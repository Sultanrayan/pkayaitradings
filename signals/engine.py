"""Bar-anchored signal engine.

The engine's contract, in one paragraph: given an OHLCV frame indexed by **bar
close time in UTC**, it returns signals whose ``timestamp`` is a key of that
index and whose ``price`` is that bar's ``close``. Nothing is inferred from a bar
that has not closed, and nothing computed for bar ``i`` depends on bar ``i + 1``.

Why the index must be close time
--------------------------------
This is the single most consequential design decision in the module, and it
differs from the rest of this codebase. ``agents.technical_analyst.strategy``
indexes by ``open_time`` because biquote returns that and the strategy only ever
reads the last row. The signal engine cannot: a signal must be plotted on the bar
the trader acted on, and on a chart the bar is labelled by its *close*. If the
index were open time while the timestamp were close time, every signal would be
plotted one bar early and the drift would be invisible in tests that only compare
against the engine's own output. :func:`frame_from_series` does the conversion so
callers never hand-index the frame themselves.

Bar closure
-----------
Whether the trailing bar has closed is decided by comparing the bar's *own* close
time against an explicitly supplied ``now``. Nothing in the engine calls
``time.time()`` (RULE 5): the clock is injected, so a backtest over fixed data is
reproducible and a live run says exactly what time it believed it was. When no
``now`` is supplied and ``confirm_on_close`` is set, the engine assumes the
trailing bar has NOT closed and skips it. That is the safe direction: it can only
delay a signal by one bar, never fabricate one early.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, cast

import numpy as np
import pandas as pd

from shared.logging import get_logger
from shared.schemas.enums import Timeframe
from shared.schemas.market import OhlcSeries
from signals.layers import build_features, score_all
from signals.models import (
    LAYER_NAMES,
    Signal,
    SignalConfig,
    levels_for,
)

_logger = get_logger(__name__)

__all__ = ["SignalEngine", "frame_from_series", "signal_close_time"]

_OHLCV_COLUMNS = ("open", "high", "low", "close")


def signal_close_time(timeframe: Timeframe | str) -> pd.Timedelta:
    """Duration of one bar for ``timeframe``.

    Accepts either a :class:`~shared.schemas.enums.Timeframe` or a **biquote
    interval string**. Both spellings occur in this codebase:
    :attr:`OhlcSeries.interval` carries the broker's ``"1h"``, while
    ``Timeframe.H1`` is ``"H1"``, and ``frame_from_series`` is handed the former.

    Returns:
        The bar duration as a :class:`pandas.Timedelta`.

    Raises:
        ValueError: If the timeframe is not supported.
    """
    from signals.models import TIMEFRAME_SECONDS

    key = _coerce_timeframe(timeframe)
    try:
        return pd.Timedelta(seconds=TIMEFRAME_SECONDS[key])
    except KeyError as exc:
        raise ValueError(f"unsupported timeframe: {timeframe!r}") from exc


def _coerce_timeframe(value: Timeframe | str) -> Timeframe:
    """Normalise a timeframe given as an enum, a ``Timeframe`` name, or a biquote interval.

    Raises:
        ValueError: If the value matches none of the three spellings.
    """
    if isinstance(value, Timeframe):
        return value
    text = str(value).strip()
    try:
        return Timeframe(text)
    except ValueError:
        pass
    for candidate in Timeframe:
        if candidate.biquote_interval == text:
            return candidate
    raise ValueError(f"unsupported timeframe: {value!r}")


def frame_from_series(series: OhlcSeries, *, drop_open_bar: bool = True) -> pd.DataFrame:
    """Convert an :class:`OhlcSeries` into this module's frame contract.

    Re-indexes from ``open_time`` to **close time** (``open_time + bar duration``)
    so the index matches what a chart plots, and optionally drops the in-progress
    bar. Dropping it is the default because an unclosed bar's close is not a fact
    yet, and a signal anchored to it would repaint as the bar finishes.

    Args:
        series: Source series from the biquote client, oldest bar first.
        drop_open_bar: Whether to exclude the bar flagged ``is_open``.

    Returns:
        Frame indexed by UTC close time with columns ``open``, ``high``, ``low``,
        ``close``, ``volume`` and ``tick_volume``, sorted ascending.
    """
    # `series.interval` is the broker's spelling ("1h"), not a Timeframe value.
    duration = signal_close_time(series.interval)
    rows = [bar for bar in series.bars if not (drop_open_bar and bar.is_open)]
    if not rows:
        return pd.DataFrame(columns=[*_OHLCV_COLUMNS, "volume", "tick_volume"])

    frame = pd.DataFrame(
        [
            {
                # open_time + duration is this bar's close time, which is the label
                # a chart shows and therefore the label the signal must carry.
                "timestamp": bar.open_time + duration,
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
                "tick_volume": bar.tick_volume,
            }
            for bar in rows
        ]
    )
    index = pd.DatetimeIndex(pd.to_datetime(frame.pop("timestamp"), utc=True), name="timestamp")
    return frame.set_index(index).sort_index()


@dataclass(frozen=True)
class _BarOutcome:
    """Internal per-bar evaluation result, before cooldown filtering."""

    position: int
    action: str
    confidence: float
    price: float
    atr: float
    sl: float
    tp1: float
    tp2: float
    scores: dict[str, float]
    reason: str


class SignalEngine:
    """Deterministic, non-repainting signal generator.

    Args:
        config: Tunables. Validated on construction, so an impossible
            configuration fails here rather than producing wrong signals later.

    The engine holds no per-call state. Every method is a pure function of its
    arguments, which is what lets the same object serve a backtest, a live poll
    and a test without cross-contamination.
    """

    def __init__(self, config: SignalConfig | None = None) -> None:
        self.config = config or SignalConfig()

    # ------------------------------------------------------------------ #
    # Input normalisation
    # ------------------------------------------------------------------ #

    def _prepare(
        self,
        df: pd.DataFrame,
        *,
        now: pd.Timestamp | None,
    ) -> tuple[pd.DataFrame, int | None]:
        """Validate and normalise an input frame.

        Returns:
            ``(frame, last_closed_position)``. The frame is a copy with a
            UTC-normalised index and the required columns present; the position is
            the index of the newest bar considered closed, or ``None`` when no bar
            qualifies.

        Raises:
            ValueError: If the frame is empty, required columns are absent, the
                index is not a DatetimeIndex, or the index is not monotonic
                increasing.
        """
        if df is None or len(df) == 0:
            # An empty frame has no index to validate and no bar to anchor to.
            # Saying so plainly beats an IndexError from deeper in the engine.
            raise ValueError("frame is empty: no bars to evaluate")

        missing = [c for c in _OHLCV_COLUMNS if c not in df.columns]
        if missing:
            raise ValueError(f"frame is missing required columns: {missing}")
        if not isinstance(df.index, pd.DatetimeIndex):
            raise ValueError(
                "frame must be indexed by a DatetimeIndex of bar CLOSE times; "
                "use signals.engine.frame_from_series to build one"
            )

        out = df.copy()
        # Re-narrow the copy's index: `copy()` erases the isinstance narrowing
        # above, and `out.index` is statically a bare Index without the cast.
        index = cast(pd.DatetimeIndex, out.index)
        if index.tz is None:
            # A naive index is a latent timezone bug. Localising to UTC is the only
            # safe reading: the alternative (assuming the feed's local zone)
            # silently shifts every signal by the offset.
            _logger.warning("signals.naive_index_assumed_utc", bars=len(out))
            index = index.tz_localize("UTC")
        else:
            index = index.tz_convert("UTC")
        out.index = index
        out = out.sort_index()

        if not out.index.is_monotonic_increasing:
            _logger.warning("signals.unsorted_index_sorted", bars=len(out))
            out = out.sort_index()

        if out.index.has_duplicates:
            # Duplicate close times make a signal ambiguous about which bar it
            # belongs to. Keep the last, which is the most recent print.
            out = out[~out.index.duplicated(keep="last")]

        last_closed = self._last_closed_position(cast(pd.DatetimeIndex, out.index), now)
        return out, last_closed

    def _last_closed_position(
        self, index: pd.DatetimeIndex, now: pd.Timestamp | None
    ) -> int | None:
        """Position of the newest bar whose close time has passed.

        A bar labelled with close time ``t`` is closed once ``t <= now``. The
        comparison is ``<=`` so a bar closing exactly now is treated as closed,
        which matches the convention that a bar's final print is available at its
        stated close time.
        """
        if len(index) == 0:
            return None
        if now is None:
            # No clock supplied. With confirm_on_close we cannot prove the trailing
            # bar closed, so we refuse to use it. Skipping can only delay a signal
            # by one bar; including an unclosed bar would let it change later.
            return len(index) - 2 if self.config.confirm_on_close else len(index) - 1
        reference = pd.Timestamp(now)
        if reference.tzinfo is None:
            reference = reference.tz_localize("UTC")
        else:
            reference = reference.tz_convert("UTC")
        closed = np.flatnonzero(index <= reference)
        if closed.size == 0:
            return None
        return int(closed[-1])

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def compute(
        self,
        df: pd.DataFrame,
        symbol: str,
        timeframe: str,
        *,
        now: pd.Timestamp | None = None,
    ) -> list[Signal]:
        """Compute signals over every confirmed, closed bar in ``df``.

        Args:
            df: OHLCV frame indexed by bar close time in UTC. See the module
                docstring for why the index must be close time.
            symbol: Instrument ticker.
            timeframe: Candle interval, used only for labelling.
            now: Injected clock. Determines which trailing bars count as closed.
                Omit it in backtests over fixed data, or in live use to have the
                engine conservatively skip the newest bar.

        Returns:
            Signals in chronological order, cooldown and duplicate suppression
            applied. A bar that produces no qualifying signal is simply absent —
            signals are sparse by design, and an empty list is a valid answer.
        """
        frame, last_closed = self._prepare(df, now=now)
        if last_closed is None or last_closed < 0:
            return []

        upper = self._warmup_bound(last_closed, len(frame))
        if upper <= 0:
            _logger.debug(
                "signals.insufficient_history",
                symbol=symbol,
                bars=last_closed + 1,
                required=self.config.warmup_bars,
            )
            return []

        outcomes: list[_BarOutcome] = []
        features = build_features(frame, self.config)
        for pos in range(upper, last_closed + 1):
            outcome = self._score_bar(features, pos)
            if outcome is not None:
                outcomes.append(outcome)

        if not outcomes:
            return []

        # Suppression runs on scored bars, not on signals, because cooldown is
        # measured in bars. A timestamp difference is a duration, not a bar count,
        # and converting between them needs the bar spacing the frame carries but
        # the signal does not.
        kept = self._apply_suppression(outcomes)
        return [self._to_signal(outcome, frame, symbol, timeframe) for outcome in kept]

    def compute_latest(
        self,
        df: pd.DataFrame,
        symbol: str,
        timeframe: str,
        *,
        now: pd.Timestamp | None = None,
    ) -> Signal | None:
        """Compute the signal for the most recent closed bar only.

        Args:
            df: OHLCV frame indexed by bar close time in UTC.
            symbol: Instrument ticker.
            timeframe: Candle interval, used only for labelling.
            now: Injected clock.

        Returns:
            The signal on the newest closed bar, or ``None`` if that bar produced
            none. Cooldown is evaluated against the full history, so a bar inside
            a cooldown correctly returns ``None`` rather than a fresh signal.
        """
        signals = self.compute(df, symbol, timeframe, now=now)
        if not signals:
            return None
        # `compute` returns chronological order, so the last element is the
        # newest. Selecting by timestamp rather than by position keeps this
        # correct if the ordering guarantee is ever relaxed.
        frame, last_closed = self._prepare(df, now=now)
        if last_closed is None:
            return None
        newest = frame.index[last_closed]
        for signal in reversed(signals):
            if signal.timestamp == newest:
                return signal
        return None

    def evaluate_bar(
        self,
        df: pd.DataFrame,
        symbol: str,
        timeframe: str,
        bar_index: pd.Timestamp,
        *,
        now: pd.Timestamp | None = None,
    ) -> Signal | None:
        """Evaluate a single bar, ignoring history before it.

        Intended for tests and replay, where isolating one bar is the point.
        Because history is discarded, cooldown cannot be evaluated here — the
        returned signal is what the bar itself qualifies for.

        Args:
            df: OHLCV frame indexed by bar close time in UTC.
            symbol: Instrument ticker.
            timeframe: Candle interval.
            bar_index: Label-based index of the bar to evaluate. Must name a bar
                that has closed.
            now: Injected clock, used to reject an unclosed bar.

        Returns:
            The signal for that bar, or ``None``.

        Raises:
            KeyError: If ``bar_index`` is not in the frame's index.
            ValueError: If the requested bar has not closed.
        """
        frame, last_closed = self._prepare(df, now=now)
        # `sort_index()` above guarantees monotonicity, so `get_loc` returns a
        # scalar position rather than a slice or a boolean mask.
        positions = cast(pd.DatetimeIndex, frame.index).get_loc(bar_index)
        if not isinstance(positions, (int, np.integer)):
            raise KeyError(f"bar {bar_index!r} not present as a unique frame index")
        position = int(positions)

        if last_closed is None or position > last_closed:
            raise ValueError(
                f"bar {bar_index.isoformat()} has not closed; refusing to evaluate it"
            )
        if position < self.config.warmup_bars - 1:
            return None
        outcome = self._score_bar(build_features(frame, self.config), position)
        if outcome is None:
            return None
        return self._to_signal(outcome, frame, symbol, timeframe)

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #

    def _warmup_bound(self, last_closed: int, total: int) -> int:
        """First position at which every layer can be evaluated.

        Bars before this are unevaluable, not filtered: they are excluded because
        their indicators are NaN, and the count is logged so a caller can tell
        "no signals" from "not enough history".
        """
        bound = self.config.warmup_bars - 1
        if bound + 1 > last_closed + 1:
            _logger.debug(
                "signals.warmup_exceeds_history",
                warmup_bars=self.config.warmup_bars,
                available=last_closed + 1,
            )
            return last_closed + 1
        return min(bound, total)

    def _score_bar(self, features: pd.DataFrame, pos: int) -> _BarOutcome | None:
        """Score one bar and decide whether it qualifies.

        Returns ``None`` when the bar produces no signal. Every rejection is
        counted so that a silent engine — one that never fires for a structural
        reason rather than a market one — is distinguishable from a quiet market.
        """
        layers = score_all(features, self.config, pos)
        scores = {name: value[0] for name, value in layers.items()}

        # Mandatory layers: each must be evaluable AND agree with the final
        # direction. A mandatory layer that could not be evaluated blocks the
        # signal. This is the mechanism that stops warmup from being papered over.
        for name in self.config.mandatory_layers:
            score, evaluable, detail = layers[name]
            if not evaluable:
                _logger.debug(
                    "signals.mandatory_layer_unevaluable",
                    layer=name,
                    position=pos,
                    detail=detail,
                )
                return None

        contributing = [n for n, (_, evaluable, _) in layers.items() if evaluable]
        if not contributing:
            return None

        # Direction from the sign of the weighted sum, where only evaluable layers
        # participate. Renormalising by the weight actually present keeps the
        # confidence in [0, 1] even when some layers abstained.
        weighted = sum(
            self.config.weights[name] * layers[name][0] for name in contributing
        )
        available_weight = sum(self.config.weights[name] for name in contributing)
        if available_weight <= 0.0:
            return None

        normalised = weighted / available_weight
        if abs(normalised) < 1e-12:
            return None

        action: Literal["BUY", "SELL"] = "BUY" if normalised > 0 else "SELL"
        # Confidence is conviction in the chosen direction, so the magnitude of the
        # signed aggregate, not the raw signed value.
        confidence = _clip01(abs(normalised))

        # Mandatory layers must agree with the direction, not merely be evaluable.
        for name in self.config.mandatory_layers:
            score = layers[name][0]
            if (action == "BUY" and score <= 0.0) or (action == "SELL" and score >= 0.0):
                _logger.debug(
                    "signals.mandatory_layer_disagrees",
                    layer=name,
                    action=action,
                    score=score,
                    position=pos,
                )
                return None

        threshold = self.config.effective_threshold
        if confidence < threshold:
            return None

        close_now = float(features["close"].iloc[pos])
        if not math.isfinite(close_now) or close_now <= 0.0:
            return None

        atr_now = float(features["atr"].iloc[pos])
        if not math.isfinite(atr_now) or atr_now <= 0.0:
            # Without ATR the levels cannot be placed. Refusing here is correct: a
            # fabricated stop is worse than no signal.
            return None

        sl, tp1, tp2 = levels_for(
            action=action,
            price=close_now,
            atr=atr_now,
            sl_mult=self.config.atr_sl_mult,
            tp_mult=self.config.atr_tp_mult,
            tp2_mult=self.config.atr_tp2_mult,
        )

        reason = _build_reason(
            action=action,
            layers=layers,
            config=self.config,
            confidence=confidence,
            threshold=threshold,
        )

        return _BarOutcome(
            position=pos,
            action=action,
            confidence=confidence,
            price=close_now,
            atr=atr_now,
            sl=sl,
            tp1=tp1,
            tp2=tp2,
            scores=scores,
            reason=reason,
        )

    def _to_signal(
        self,
        outcome: _BarOutcome,
        frame: pd.DataFrame,
        symbol: str,
        timeframe: str,
    ) -> Signal:
        """Materialise a scored bar into a frozen :class:`Signal`.

        The timestamp is taken from the frame's index and the price from the same
        bar's close, in the same breath. Reading them together is what guarantees
        RULE 2: there is no path where the two can come from different bars.
        """
        return Signal(
            timestamp=frame.index[outcome.position],
            symbol=symbol.upper(),
            timeframe=str(timeframe),
            action=outcome.action,  # type: ignore[arg-type]
            price=outcome.price,
            entry=outcome.price,
            sl=outcome.sl,
            tp1=outcome.tp1,
            tp2=outcome.tp2,
            atr=outcome.atr,
            confidence=outcome.confidence,
            reason=outcome.reason,
            layers=dict(outcome.scores),
        )

    def _apply_suppression(self, outcomes: Sequence[_BarOutcome]) -> list[_BarOutcome]:
        """Apply cooldown and duplicate-direction suppression.

        Two independent rules:

        * **Cooldown** — at least ``min_bars_between_signals`` bars between two
          emitted signals. Without it a sustained move emits a signal on every
          bar. Measured in *positional* distance, so a gap in the data does not
          silently count as many bars of cooldown.
        * **Opposite-first** — with ``require_opposite_before_repeat``, a BUY may
          not follow a BUY until a SELL intervenes. This is a statement about
          *intent*: consecutive same-direction signals are one idea expressed
          repeatedly, and plotting each one double-counts it on the chart.

        Returns:
            The surviving scored bars, still chronological.
        """
        kept: list[_BarOutcome] = []
        last_position: int | None = None
        last_action: str | None = None

        for outcome in outcomes:
            within_cooldown = (
                last_position is not None
                and outcome.position - last_position < self.config.min_bars_between_signals
            )
            if within_cooldown:
                continue
            if (
                self.config.require_opposite_before_repeat
                and last_action is not None
                and outcome.action == last_action
            ):
                continue
            kept.append(outcome)
            last_position = outcome.position
            last_action = outcome.action

        return kept


def _clip01(value: float) -> float:
    """Clamp into ``[0, 1]``, mapping NaN to 0.0."""
    if value is None or not math.isfinite(value):
        return 0.0
    return float(min(1.0, max(0.0, value)))


def _build_reason(
    *,
    action: str,
    layers: dict[str, tuple[float, bool, str]],
    config: SignalConfig,
    confidence: float,
    threshold: float,
) -> str:
    """Compose the human-readable justification.

    Names only the layers that actually voted, in weight order, so the string
    explains the signal rather than restating the configuration.
    """
    contributing = [n for n in LAYER_NAMES if layers.get(n, (0.0, False, ""))[1]]
    parts = [f"{action} at {confidence:.2f} confidence (threshold {threshold:.2f})"]
    for name in contributing:
        score, _, detail = layers[name]
        sign = "+" if score >= 0 else ""
        parts.append(f"{name} {sign}{score:.2f} ({detail})")
    skipped = [n for n in LAYER_NAMES if not layers.get(n, (0.0, False, ""))[1]]
    if skipped:
        parts.append(f"not evaluated: {', '.join(skipped)}")
    return " | ".join(parts)
