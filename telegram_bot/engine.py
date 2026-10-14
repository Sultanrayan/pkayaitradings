"""Signal computation — the no-repaint boundary.

This module owns the single most important guarantee in the bot: **a signal is
computed only on a bar that has closed, and it never changes afterwards.**

How closure is decided
----------------------
A bar indexed by close time ``t`` is closed once ``t <= now``. The clock is
injected rather than read here, so a backtest over fixed data is reproducible and
a live scan says exactly what time it believed it was. When no ``now`` is given
the trailing bar is treated as **unclosed** and skipped — that direction can only
delay a signal by one bar, never fabricate one early.

Why the frame must be indexed by CLOSE time
--------------------------------------------
A chart labels a candle by when it closed. If the engine indexed by open time and
the message carried an open time, every signal would be plotted one bar early and
no test comparing the engine only to itself would catch it. :func:`to_closed_frame`
converts a feed series into this contract so no caller hand-builds it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, cast

import numpy as np
import pandas as pd

from shared.schemas.market import OhlcSeries
from telegram_bot.defaults import BotConfig
from telegram_bot.layers import LAYER_NAMES, LAYER_WEIGHTS, LayerScores, compute_layers
from telegram_bot.narrative import (
    band_strength,
    build_explanation,
    build_invalidation,
    build_recommendation,
    build_risk_notes,
)
from telegram_bot.orderflow import OrderFlowSnapshot
from telegram_bot.timeframes import bar_seconds

__all__ = [
    "Signal",
    "bar_close_seconds",
    "compute_signal",
    "describe_rejection",
    "last_closed_position",
    "reward_to_risk",
    "to_closed_frame",
    "update_signal_outcome",
]

Action = Literal["BUY", "SELL"]

#: Which level of TP/SL counts as "won". TP1 is the realistic target; TP2 is the
#: runner.
OUTCOME_TARGET = 1


def reward_to_risk(entry: float, sl: float, tp2: float) -> float:
    """Reward-to-risk of a trade, measured against TP2.

    This is the *only* definition of the ratio in the codebase. The card, the
    confluence card, ``/status`` and ``/performance`` all call it, because the
    required UI format prints ``RR: 1:2.0`` on a sample whose TP1 sits exactly
    one risk unit away — only a TP2-based ratio produces that figure.

    Args:
        entry: Entry price.
        sl: Stop-loss price.
        tp2: Final take-profit price.

    Returns:
        Reward divided by risk, or ``0.0`` when the stop equals the entry and the
        ratio is undefined. A zero stop is a malformed signal, and reporting it
        as an infinite risk/reward would be the more misleading of the two.
    """
    risk = abs(entry - sl)
    if risk <= 0.0:
        return 0.0
    return abs(tp2 - entry) / risk


@dataclass(frozen=True)
class Signal:
    """A signal anchored to one closed candle.

    Attributes:
        symbol: Instrument ticker.
        timeframe: Internal timeframe.
        bar_ts: Unix seconds of the anchor bar's close.
        action: ``BUY`` or ``SELL``.
        entry: Entry price — the anchor bar's close.
        sl: Stop-loss.
        tp1: First take-profit.
        tp2: Second take-profit.
        confidence: Weighted agreement in ``[0, 1]``.
        layers: Per-layer scores keyed by name.
        order_flow: The order-flow snapshot for the bar.
        reason: Why no signal fired, or why one did.
        is_confluence: Set later when the confluence check runs.
        confluence_tfs: Timeframes participating in a confluence.
    """

    symbol: str
    timeframe: str
    bar_ts: int
    action: Action
    entry: float
    sl: float
    tp1: float
    tp2: float
    confidence: float
    layers: dict[str, float]
    order_flow: OrderFlowSnapshot
    reason: str
    is_confluence: bool = False
    confluence_tfs: tuple[str, ...] = ()

    # --- Narrative fields, derived from the bot's own indicators ---
    #
    # Populated by :func:`compute_signal` from the bot's seven layers, ATR and
    # swing structure. They default to empty so a hand-built Signal in a test
    # does not have to supply prose.
    strength: str = ""
    recommendation: str = ""
    explanation: str = ""
    risk_notes: str = ""
    invalidation: str = ""

    @property
    def risk_reward(self) -> float:
        """Reward-to-risk against TP2 — the same ratio the card displays.

        Deliberately not TP1: the required UI format prints ``RR: 1:2.0`` where
        the sample has TP1 at exactly the risk distance, so the shown figure can
        only have come from TP2. Measuring TP1 here while the formatter measured
        TP2 would let the card and the performance average quietly disagree.
        """
        return reward_to_risk(self.entry, self.sl, self.tp2)

    def to_record(self, *, sent_at: int) -> dict[str, Any]:
        """Row payload for the ``signals`` table."""
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "timestamp": self.bar_ts,
            "action": self.action,
            "entry": self.entry,
            "sl": self.sl,
            "tp1": self.tp1,
            "tp2": self.tp2,
            "confidence": self.confidence,
            "layers": dict(self.layers),
            "order_flow": self.order_flow.to_dict(),
            "reason": self.reason,
            "strength": self.strength,
            "recommendation": self.recommendation,
            "explanation": self.explanation,
            "risk_notes": self.risk_notes,
            "invalidation": self.invalidation,
            "is_confluence": self.is_confluence,
            "confluence_tfs": list(self.confluence_tfs),
            "sent_at": sent_at,
        }

    def with_confluence(self, timeframes: tuple[str, ...]) -> Signal:
        """Copy marked as a confluence across ``timeframes``."""
        return Signal(
            symbol=self.symbol,
            timeframe=self.timeframe,
            bar_ts=self.bar_ts,
            action=self.action,
            entry=self.entry,
            sl=self.sl,
            tp1=self.tp1,
            tp2=self.tp2,
            confidence=self.confidence,
            layers=dict(self.layers),
            order_flow=self.order_flow,
            reason=self.reason,
            is_confluence=True,
            confluence_tfs=timeframes,
            strength=self.strength,
            recommendation=self.recommendation,
            explanation=self.explanation,
            risk_notes=self.risk_notes,
            invalidation=self.invalidation,
        )


def bar_close_seconds(index: pd.Index) -> np.ndarray:
    """Bar close times as Unix seconds.

    One helper for every call site. ``DatetimeIndex.view("int64")`` and
    ``.astype("int64")`` both return a bare ndarray under pandas 3, so the
    conversion goes through ``.values`` explicitly rather than chaining methods
    that a future pandas may move again.

    Args:
        index: Bar close times, timezone-aware. Typed as ``pd.Index`` because
            every caller passes ``frame.index``, which pandas types as the base
            class even when the values are timestamps.

    Returns:
        Array of Unix seconds.

    Raises:
        ValueError: If the index is timezone-naive, where the intended instant is
            ambiguous and guessing would misplace signals.
    """
    stamps = cast(pd.DatetimeIndex, index)
    if stamps.tz is None:
        raise ValueError("bar index must be timezone-aware; naive times are ambiguous")
    return np.asarray(stamps.values, dtype="datetime64[s]").astype("int64")


def to_closed_frame(series: OhlcSeries, timeframe: str) -> pd.DataFrame:
    """Convert a feed series into this module's contract.

    Re-indexes from the feed's ``open_time`` to the bar's **close** time and drops
    the in-progress bar. Both steps are required, not cosmetic: an unclosed bar's
    close is not a fact yet, and an open-time label would misplace every marker by
    a bar.

    Args:
        series: Feed series, oldest-first.
        timeframe: Internal timeframe, needed to compute each bar's close time.

    Returns:
        Frame indexed by UTC close time with ``open``/``high``/``low``/``close``/
        ``volume``/``tick_volume``. Empty when the series has no closed bars.
    """
    seconds = bar_seconds(timeframe)
    rows = [bar for bar in series.bars if not bar.is_open]
    if not rows:
        return pd.DataFrame(
            columns=["open", "high", "low", "close", "volume", "tick_volume"]
        )

    frame = pd.DataFrame(
        [
            {
                "close_time": bar.open_time.timestamp() + seconds,
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
    index = pd.DatetimeIndex(
        pd.to_datetime(frame.pop("close_time"), unit="s", utc=True), name="close_time"
    )
    return frame.set_index(index).sort_index()


def last_closed_position(index: pd.Index, now: int | None, confirm: bool) -> int | None:
    """Position of the newest bar that has closed.

    Args:
        index: Bar close times. Typed as ``pd.Index`` because every caller passes
            ``frame.index``.
        now: Unix seconds. ``None`` means "unknown".
        confirm: When ``True`` and ``now`` is ``None``, the trailing bar is
            assumed unclosed and skipped.

    Returns:
        Positional index, or ``None`` when no bar has closed.
    """
    if len(index) == 0:
        return None
    if now is None:
        if not confirm:
            return len(index) - 1
        return len(index) - 2 if len(index) >= 2 else None
    closes = bar_close_seconds(index)
    closed = np.flatnonzero(closes <= int(now))
    if closed.size == 0:
        return None
    return int(closed[-1])


def compute_signal(
    frame: pd.DataFrame,
    *,
    symbol: str,
    timeframe: str,
    config: BotConfig,
    now: int | None = None,
    position: int | None = None,
) -> Signal | None:
    """Compute the signal for the newest closed bar of ``frame``.

    Args:
        frame: Closed-bar OHLCV frame indexed by close time in UTC.
        symbol: Instrument ticker.
        timeframe: Internal timeframe.
        config: Bot configuration supplying the threshold and risk multipliers.
        now: Injected clock. ``None`` means the trailing bar is treated as
            unclosed.
        position: Evaluate a specific bar instead of the newest closed one. Used
            by the confluence check and by tests.

    Returns:
        A signal when the layers agree at or above the threshold, otherwise
        ``None``. A quiet market and a warmup both yield ``None``; they are
        distinguished by :func:`describe_rejection`.
    """
    if frame is None or len(frame) == 0:
        return None

    if position is None:
        pos = last_closed_position(frame.index, now, confirm=True)
        if pos is None:
            return None
    else:
        pos = position

    window = frame.iloc[: pos + 1]
    if len(window) < 30:
        # Below the point where even the fastest layer has data.
        return None

    scores = compute_layers(window, symbol=symbol, timeframe=timeframe, position=-1)

    evaluable = [n for n in LAYER_NAMES if scores.results[n].evaluable]
    if not evaluable:
        return None

    weighted = sum(LAYER_WEIGHTS[n] * scores.results[n].score for n in evaluable)
    available = sum(LAYER_WEIGHTS[n] for n in evaluable)
    if available <= 0.0:
        return None

    normalised = weighted / available
    if abs(normalised) < 1e-12:
        return None

    confidence = min(1.0, abs(normalised))
    if confidence < config.confidence_min:
        return None

    risk = config.risk_for(symbol)
    close_now = float(window["close"].iloc[-1])
    if not np.isfinite(close_now) or close_now <= 0.0:
        return None

    atr_value = float(window["atr"].iloc[-1]) if "atr" in window.columns else float("nan")
    if not np.isfinite(atr_value) or atr_value <= 0.0:
        atr_series = _atr(window, risk.atr_period)
        if atr_series is None:
            return None
        atr_value = atr_series

    action: Action = "BUY" if normalised > 0 else "SELL"
    if action == "BUY":
        sl = close_now - risk.sl_atr_mult * atr_value
        tp1 = close_now + risk.tp1_atr_mult * atr_value
        tp2 = close_now + risk.tp2_atr_mult * atr_value
    else:
        sl = close_now + risk.sl_atr_mult * atr_value
        tp1 = close_now - risk.tp1_atr_mult * atr_value
        tp2 = close_now - risk.tp2_atr_mult * atr_value

    layer_scores = {n: scores.results[n].score for n in LAYER_NAMES}
    layer_details = {n: scores.results[n].detail for n in LAYER_NAMES}
    layer_evaluable = {n: scores.results[n].evaluable for n in LAYER_NAMES}

    # Nearest structural level the bot can see for itself: support under a long,
    # resistance under a short. Taken from the swing/fib work already in the frame
    # rather than recomputed, so it cannot disagree with the card.
    structure: float | None = None
    if "swing_low_price" in window.columns and action == "BUY":
        candidate = window["swing_low_price"].iloc[-1]
        structure = float(candidate) if np.isfinite(candidate) else None
    elif "swing_high_price" in window.columns and action == "SELL":
        candidate = window["swing_high_price"].iloc[-1]
        structure = float(candidate) if np.isfinite(candidate) else None

    strength = band_strength(confidence)

    return Signal(
        symbol=symbol.upper(),
        timeframe=timeframe,
        bar_ts=int(window.index[-1].timestamp()),
        action=action,
        entry=close_now,
        sl=sl,
        tp1=tp1,
        tp2=tp2,
        confidence=confidence,
        layers=layer_scores,
        order_flow=scores.order_flow,
        reason=_reason(scores, confidence, config.confidence_min),
        strength=strength,
        recommendation=build_recommendation(action, strength, confidence),
        explanation=build_explanation(
            action=action,
            confidence=confidence,
            layers=layer_scores,
            details=layer_details,
            evaluable=layer_evaluable,
        ),
        risk_notes=build_risk_notes(
            action=action,
            layers=layer_scores,
            details=layer_details,
            order_flow=scores.order_flow,
            sl=sl,
            entry=close_now,
        ),
        invalidation=build_invalidation(
            action=action,
            entry=close_now,
            sl=sl,
            structure=structure,
            atr=atr_value,
            timeframe=timeframe,
        ),
    )


def _atr(frame: pd.DataFrame, period: int) -> float | None:
    """ATR of the frame's final bar, or ``None`` when unavailable."""
    from telegram_bot import indicators as ind

    series = ind.atr(frame["high"], frame["low"], frame["close"], period)
    if series.empty:
        return None
    value = float(series.iloc[-1])
    return value if np.isfinite(value) and value > 0.0 else None


def describe_rejection(
    frame: pd.DataFrame,
    *,
    symbol: str,
    timeframe: str,
    config: BotConfig,
    now: int | None = None,
) -> dict[str, Any]:
    """Explain why a bar produced no signal.

    The ``/agenza`` command shows this when there is no signal, so "nothing fired"
    is always accompanied by the reason rather than being silent.

    Returns:
        Dict with the layer scores and a human-readable ``reason``.
    """
    pos = last_closed_position(frame.index, now, confirm=True)
    if pos is None:
        return {"layers": {}, "confidence": 0.0, "reason": "No closed bar available"}

    window = frame.iloc[: pos + 1]
    scores = compute_layers(window, symbol=symbol, timeframe=timeframe, position=-1)

    evaluable = [n for n in LAYER_NAMES if scores.results[n].evaluable]
    if evaluable:
        weighted = sum(LAYER_WEIGHTS[n] * scores.results[n].score for n in evaluable)
        available = sum(LAYER_WEIGHTS[n] for n in evaluable)
        confidence = min(1.0, abs(weighted / available)) if available > 0 else 0.0
    else:
        confidence = 0.0

    return {
        "layers": {n: scores.results[n] for n in LAYER_NAMES},
        "scores": scores,
        "confidence": confidence,
        "reason": _rejection_reason(scores, config.confidence_min),
    }


def _reason(scores: LayerScores, confidence: float, threshold: float) -> str:
    """Justification for a fired signal."""
    parts = [f"{confidence:.0%} of {threshold:.0%} threshold met"]
    for name in LAYER_NAMES:
        result = scores.results[name]
        if result.evaluable and abs(result.score) > 0.2:
            parts.append(f"{name} {result.score:+.2f}")
    return ", ".join(parts)


def _rejection_reason(scores: LayerScores, threshold: float) -> str:
    """Why no signal fired, naming the layers that blocked it."""
    evaluable = [n for n in LAYER_NAMES if scores.results[n].evaluable]
    if not evaluable:
        return "Indicators still warming up"

    blocking = [
        name
        for name in evaluable
        if abs(scores.results[name].score) < 0.2
    ]
    directional = [
        name
        for name in evaluable
        if abs(scores.results[name].score) >= 0.2
    ]
    if directional and any(scores.results[n].score > 0 for n in directional) and any(
        scores.results[n].score < 0 for n in directional
    ):
        return "Layers disagree on direction"
    if blocking:
        return "Weak: " + ", ".join(n.replace("_", " ") for n in blocking[:3])
    return f"Below {threshold:.2f} threshold"


def update_signal_outcome(
    signal: Signal,
    *,
    high: float,
    low: float,
) -> str | None:
    """Resolve a stored signal against a later bar's range.

    Conservative by design: when both the stop and the target fall inside one
    bar's range, the **stop is assumed to have been hit first**. That ordering is
    unknowable from OHLC and assuming the favourable one would inflate every win
    rate the bot reports.

    Args:
        signal: The stored signal.
        high: The later bar's high.
        low: The later bar's low.

    Returns:
        ``"win"``, ``"loss"``, or ``None`` while the trade is still live.
    """
    if signal.action == "BUY":
        stop_hit = low <= signal.sl
        target_hit = high >= signal.tp1
    else:
        stop_hit = high >= signal.sl
        target_hit = low <= signal.tp1

    if stop_hit:
        return "loss"
    if target_hit:
        return "win"
    return None


def pnl_for(signal: Signal, outcome: str, exit_price: float) -> float:
    """Percentage move realised by a signal, signed."""
    if signal.entry == 0.0:
        return 0.0
    move = (exit_price - signal.entry) / signal.entry * 100.0
    return move if signal.action == "BUY" else -move


def exit_price_for(signal: Signal, outcome: str) -> float:
    """The price a resolved outcome exited at — TP1 or SL."""
    return signal.tp1 if outcome == "win" else signal.sl
