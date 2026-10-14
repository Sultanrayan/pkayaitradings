"""Data models for the bar-anchored signal engine.

Every model here is frozen. A signal, once computed, is a statement about one
specific bar at one specific moment; if the market later disagrees, the correct
outcome is a *new* signal or no signal, never a mutation of the old one. Frozen
dataclasses make that a type-level guarantee rather than a convention.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Literal

import pandas as pd

from shared.schemas.enums import Timeframe

__all__ = [
    "Action",
    "LayerScore",
    "Signal",
    "SignalConfig",
    "SignalMode",
]

#: Directional action. There is deliberately no WAIT/HOLD member: the absence of
#: a signal is represented by ``None``, not by a sentinel direction. A caller
#: that must branch on three cases can treat ``None`` as the third.
Action = Literal["BUY", "SELL"]

#: Engine operating modes, mapped to their confidence thresholds in
#: :data:`CONFIDENCE_THRESHOLDS`.
SignalMode = Literal["aggressive", "balanced", "conservative"]

#: Confidence a signal must reach before it is emitted, per mode.
CONFIDENCE_THRESHOLDS: dict[str, float] = {
    "aggressive": 0.40,
    "balanced": 0.60,
    "conservative": 0.75,
}

#: Canonical layer names. The order is also the reporting order.
LAYER_NAMES: tuple[str, ...] = (
    "trend",
    "momentum",
    "volume",
    "price_action",
    "volatility",
    "support_resistance",
)

#: Default per-layer weights. These sum to 1.0, so a layer's contribution to the
#: confidence is bounded by its weight.
DEFAULT_WEIGHTS: dict[str, float] = {
    "trend": 0.25,
    "momentum": 0.25,
    "volume": 0.15,
    "price_action": 0.15,
    "volatility": 0.10,
    "support_resistance": 0.10,
}

#: Bar duration per timeframe, in seconds. Used to derive a bar's close time from
#: its open time, and to decide whether the newest bar has closed.
TIMEFRAME_SECONDS: dict[Timeframe, int] = {
    Timeframe.M1: 60,
    Timeframe.M5: 300,
    Timeframe.M15: 900,
    Timeframe.M30: 1_800,
    Timeframe.H1: 3_600,
    Timeframe.H4: 14_400,
    Timeframe.D1: 86_400,
}


@dataclass(frozen=True)
class LayerScore:
    """One confirmation layer's verdict on one bar.

    Attributes:
        name: Layer name from :data:`LAYER_NAMES`.
        score: Directional score in ``[-1, 1]``. Positive favours BUY, negative
            favours SELL, zero is neutral. A layer that cannot be evaluated
            (insufficient warmup) reports ``0.0`` and sets ``evaluable=False``
            rather than being silently omitted.
        evaluable: Whether the layer had enough data to form an opinion. A
            non-evaluable layer contributes nothing to confidence.
        detail: Human-readable justification, surfaced in the signal reason.
    """

    name: str
    score: float
    evaluable: bool
    detail: str = ""


@dataclass(frozen=True)
class SignalConfig:
    """Tunables for :class:`~signals.engine.SignalEngine`.

    Defaults are the "balanced" profile from the specification. Every field is
    validated in ``__post_init__`` so an impossible configuration fails at
    construction rather than producing quietly wrong signals later.

    Attributes:
        mode: Operating mode; selects the confidence threshold.
        confidence_threshold: Explicit threshold. When ``None``, the value for
            ``mode`` is used.
        min_bars_between_signals: Minimum bars between two signals for the same
            symbol and timeframe.
        confirm_on_close: When ``True`` (the default) an unclosed trailing bar is
            never evaluated.
        require_opposite_before_repeat: When ``True`` a BUY may not follow a BUY
            until a SELL has intervened, and vice versa.
        mandatory_layers: Layers that must be evaluable and directionally agree
            for a signal to fire.
        weights: Per-layer weights. Must cover exactly :data:`LAYER_NAMES` and
            sum to 1.0.
        atr_period: Lookback for Average True Range.
        atr_sl_mult: Stop-loss distance as a multiple of ATR.
        atr_tp_mult: First take-profit distance as a multiple of ATR.
        atr_tp2_mult: Second take-profit distance as a multiple of ATR.
        ema_fast: Fast EMA period.
        ema_slow: Slow EMA period.
        adx_period: ADX lookback.
        adx_trend_min: ADX floor below which the trend layer is not evaluable.
        rsi_period: RSI lookback.
        rsi_oversold: RSI level at or below which momentum reads bullish.
        rsi_overbought: RSI level at or above which momentum reads bearish.
        volume_ma_period: Lookback for the volume moving average.
        volume_mult: Volume must exceed this multiple of its moving average.
        atr_min_ratio: Minimum ATR/close ratio for the volatility layer.
        atr_max_ratio: Maximum ATR/close ratio for the volatility layer.
        bb_period: Bollinger Band period, used for the squeeze check.
        bb_std: Bollinger Band standard deviations.
        sr_lookback: Swing lookback for support/resistance pivots.
        sr_atr_mult: Proximity to a level, in ATR multiples, that scores a hit.
    """

    mode: SignalMode = "balanced"
    confidence_threshold: float | None = None
    min_bars_between_signals: int = 5
    confirm_on_close: bool = True
    require_opposite_before_repeat: bool = True
    mandatory_layers: tuple[str, ...] = ("trend",)
    weights: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))

    atr_period: int = 14
    atr_sl_mult: float = 1.5
    atr_tp_mult: float = 2.5
    atr_tp2_mult: float = 4.0

    ema_fast: int = 50
    ema_slow: int = 200
    adx_period: int = 14
    adx_trend_min: float = 20.0

    rsi_period: int = 14
    rsi_oversold: float = 30.0
    rsi_overbought: float = 70.0

    volume_ma_period: int = 20
    volume_mult: float = 1.2

    atr_min_ratio: float = 0.0005
    atr_max_ratio: float = 0.05
    bb_period: int = 20
    bb_std: float = 2.0

    sr_lookback: int = 5
    sr_atr_mult: float = 1.0

    def __post_init__(self) -> None:
        """Reject configurations that cannot produce meaningful signals.

        Raises:
            ValueError: If weights do not match the layer set or do not sum to
                1.0, if a mandatory layer is unknown, if a period is too small,
                or if the SL/TP multipliers are not positive.
        """
        unknown = set(self.weights) - set(LAYER_NAMES)
        if unknown:
            raise ValueError(f"unknown layers in weights: {sorted(unknown)}")
        missing = set(LAYER_NAMES) - set(self.weights)
        if missing:
            raise ValueError(f"missing layers in weights: {sorted(missing)}")
        total = sum(self.weights.values())
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"weights must sum to 1.0, got {total!r}")
        if any(w < 0.0 for w in self.weights.values()):
            raise ValueError("weights must be non-negative")

        bad_mandatory = set(self.mandatory_layers) - set(LAYER_NAMES)
        if bad_mandatory:
            raise ValueError(f"unknown mandatory layers: {sorted(bad_mandatory)}")

        if self.mode not in CONFIDENCE_THRESHOLDS:
            raise ValueError(
                f"mode must be one of {sorted(CONFIDENCE_THRESHOLDS)}, got {self.mode!r}"
            )
        threshold = self.effective_threshold
        if not 0.0 <= threshold <= 1.0:
            raise ValueError(f"confidence_threshold must be in [0, 1], got {threshold}")

        if self.min_bars_between_signals < 0:
            raise ValueError("min_bars_between_signals must be non-negative")

        for name in (
            "atr_period",
            "ema_fast",
            "ema_slow",
            "adx_period",
            "rsi_period",
            "volume_ma_period",
            "bb_period",
            "sr_lookback",
        ):
            if getattr(self, name) < 2:
                raise ValueError(f"{name} must be at least 2, got {getattr(self, name)}")
        if self.ema_fast >= self.ema_slow:
            raise ValueError(
                f"ema_fast ({self.ema_fast}) must be smaller than ema_slow ({self.ema_slow})"
            )
        if not 0.0 < self.rsi_oversold < self.rsi_overbought < 100.0:
            raise ValueError("require 0 < rsi_oversold < rsi_overbought < 100")
        if self.volume_mult <= 0.0:
            raise ValueError("volume_mult must be positive")
        if not 0.0 < self.atr_min_ratio < self.atr_max_ratio:
            raise ValueError("require 0 < atr_min_ratio < atr_max_ratio")
        if self.sr_atr_mult <= 0.0:
            raise ValueError("sr_atr_mult must be positive")
        for name in ("atr_sl_mult", "atr_tp_mult", "atr_tp2_mult"):
            if getattr(self, name) <= 0.0:
                raise ValueError(f"{name} must be positive")
        if self.atr_tp_mult >= self.atr_tp2_mult:
            raise ValueError("require atr_tp_mult < atr_tp2_mult")

    @property
    def effective_threshold(self) -> float:
        """The confidence threshold in force: explicit value, else the mode's."""
        if self.confidence_threshold is not None:
            return float(self.confidence_threshold)
        return CONFIDENCE_THRESHOLDS[self.mode]

    @property
    def warmup_bars(self) -> int:
        """Bars required before every layer can be evaluated.

        The binding constraint is the slowest indicator plus the swing lookback.
        Bars before this point are *unevaluable*, not filtered out — they simply
        cannot produce a signal, and the engine reports how many there were.
        """
        return max(
            self.ema_slow,
            self.ema_fast + self.sr_lookback,
            self.bb_period,
            self.volume_ma_period,
            self.rsi_period + 1,
            self.atr_period + 1,
            self.sr_lookback * 2 + 1,
        )


@dataclass(frozen=True)
class Signal:
    """A directional signal anchored to one confirmed, closed candle.

    Immutability is the point: ``timestamp`` is the bar's close time and ``price``
    is that same bar's close. Any layer of the system — store, API, chart — that
    reports this signal must report these exact values, which is what makes
    "the plotted signal matches the stored signal" checkable rather than hoped for.

    Attributes:
        timestamp: UTC close time of the bar the signal is anchored to. This is
            a key of the source frame's index, by contract.
        symbol: Instrument ticker, upper-cased.
        timeframe: Candle interval.
        action: ``BUY`` or ``SELL``.
        price: Close of the anchor bar.
        entry: Reference entry price. Equal to ``price`` for a market entry on
            the bar close; kept distinct so a future limit-entry variant does not
            need a schema change.
        sl: Stop-loss level, ``atr_sl_mult`` ATRs away on the losing side.
        tp1: First take-profit, ``atr_tp_mult`` ATRs away on the winning side.
        tp2: Second take-profit, ``atr_tp2_mult`` ATRs away.
        atr: ATR on the anchor bar, the basis for all three levels.
        confidence: Weighted layer agreement in ``[0, 1]``.
        reason: Human-readable justification naming the contributing layers.
        layers: Per-layer scores keyed by layer name, each in ``[-1, 1]``.
        strategy_version: Identifies the configuration that produced this signal.
    """

    timestamp: pd.Timestamp
    symbol: str
    timeframe: str
    action: Action
    price: float
    entry: float
    sl: float
    tp1: float
    tp2: float
    atr: float
    confidence: float
    reason: str
    layers: dict[str, float]
    strategy_version: str = "1"

    def to_dict(self) -> dict[str, Any]:
        """JSON-ready representation.

        The timestamp is emitted as an ISO-8601 string in UTC so the payload is
        identical in the store, the API and the chart. ``layers`` is copied so a
        caller cannot mutate the signal through the returned dict.
        """
        return {
            "timestamp": self.timestamp.isoformat(),
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "action": self.action,
            "price": self.price,
            "entry": self.entry,
            "sl": self.sl,
            "tp1": self.tp1,
            "tp2": self.tp2,
            "atr": self.atr,
            "confidence": self.confidence,
            "reason": self.reason,
            "layers": dict(self.layers),
            "strategy_version": self.strategy_version,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Signal:
        """Rebuild a signal from :meth:`to_dict` output.

        The timestamp is re-parsed to UTC. A naive timestamp is localised rather
        than assumed, so a payload that lost its offset cannot silently shift the
        bar by hours.

        Raises:
            ValueError: If the timestamp cannot be parsed.
        """
        raw = payload["timestamp"]
        timestamp = pd.Timestamp(raw)
        if timestamp.tzinfo is None:
            timestamp = timestamp.tz_localize("UTC")
        else:
            timestamp = timestamp.tz_convert("UTC")
        action = payload["action"]
        if action not in ("BUY", "SELL"):
            raise ValueError(f"unknown action: {action!r}")
        return cls(
            timestamp=timestamp,
            symbol=str(payload["symbol"]).upper(),
            timeframe=str(payload["timeframe"]),
            action=action,
            price=float(payload["price"]),
            entry=float(payload["entry"]),
            sl=float(payload["sl"]),
            tp1=float(payload["tp1"]),
            tp2=float(payload["tp2"]),
            atr=float(payload["atr"]),
            confidence=float(payload["confidence"]),
            reason=str(payload.get("reason", "")),
            layers=dict(payload.get("layers", {})),
            strategy_version=str(payload.get("strategy_version", "1")),
        )

    def with_levels(
        self,
        *,
        sl: float,
        tp1: float,
        tp2: float,
    ) -> Signal:
        """Return a copy with different levels.

        A frozen dataclass cannot be edited, so a level revision produces a new
        instance. This exists so that intent is explicit at the call site rather
        than a caller reaching for ``object.__setattr__``.
        """
        return replace(self, sl=sl, tp1=tp1, tp2=tp2)


def levels_for(
    *,
    action: Action,
    price: float,
    atr: float,
    sl_mult: float,
    tp_mult: float,
    tp2_mult: float,
) -> tuple[float, float, float]:
    """Compute stop-loss and two take-profit levels from ATR.

    Returns:
        ``(sl, tp1, tp2)``. For a BUY the stop sits below entry and the targets
        above; for a SELL the geometry is mirrored.
    """
    if action == "BUY":
        return (
            price - sl_mult * atr,
            price + tp_mult * atr,
            price + tp2_mult * atr,
        )
    return (
        price + sl_mult * atr,
        price - tp_mult * atr,
        price - tp2_mult * atr,
    )
