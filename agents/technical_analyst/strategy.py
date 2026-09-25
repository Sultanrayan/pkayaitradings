"""Rule-based technical strategy engine.

Turns an OHLC series into a directional :class:`~shared.schemas.signals.TechnicalSignal`
by scoring four independent, well-understood edges and combining them into a
single ``[-1, 1]`` composite:

======================  =======  ==========================================
Component               Weight   Interpretation
======================  =======  ==========================================
EMA trend (fast/slow)     0.30   Fast above slow ⇒ bullish trend
MACD histogram            0.25   Positive and rising ⇒ bullish momentum
RSI                       0.20   Deviation from 50 ⇒ momentum bias
Bollinger position        0.15   Outside a band ⇒ mean-reversion bias
Short-term momentum       0.10   Close vs. short SMA
======================  =======  ==========================================

ADX acts as a trend filter: a weak trend dampens the confidence of directional
calls, which is how the engine avoids over-trading ranging markets.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from agents.technical_analyst.indicators import (
    adx,
    atr,
    bollinger_bands,
    ema,
    macd,
    rsi,
    sma,
)
from shared.schemas.enums import Direction
from shared.schemas.market import OhlcSeries
from shared.schemas.signals import IndicatorSnapshot, KeyLevels

_MIN_BARS = 60


@dataclass(frozen=True)
class TechnicalParams:
    """Indicator parameters for the technical strategy."""

    rsi_period: int = 14
    ema_fast: int = 50
    ema_slow: int = 200
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    atr_period: int = 14
    bb_period: int = 20
    bb_std: float = 2.0
    adx_period: int = 14
    momentum_period: int = 20
    level_lookback: int = 50
    neutral_threshold: float = 0.15
    strong_trend_adx: float = 25.0


@dataclass(frozen=True)
class StrategyResult:
    """The output of :func:`evaluate`."""

    signal: Direction
    confidence: float
    price: float
    indicators: IndicatorSnapshot
    key_levels: KeyLevels
    composite: float
    trend_strength: float
    reasons: list[str] = field(default_factory=list)


def to_frame(series: OhlcSeries) -> pd.DataFrame:
    """Convert an :class:`OhlcSeries` into an indexed OHLCV frame (oldest-first)."""
    if not series.bars:
        return pd.DataFrame(columns=["open", "high", "low", "close", "tick_volume"])
    frame = pd.DataFrame(
        [
            {
                "open_time": bar.open_time,
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "tick_volume": bar.tick_volume,
                "is_open": bar.is_open,
            }
            for bar in series.bars
        ]
    )
    return frame.set_index("open_time").sort_index()


def compute_indicators(frame: pd.DataFrame, params: TechnicalParams) -> pd.DataFrame:
    """Return a copy of ``frame`` with indicator columns appended."""
    required = {"open", "high", "low", "close"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"OHLC frame is missing columns: {sorted(missing)}")

    out = frame.copy()
    close = out["close"]
    out["ema_fast"] = ema(close, params.ema_fast)
    out["ema_slow"] = ema(close, params.ema_slow)
    out["sma_short"] = sma(close, params.momentum_period)
    out["rsi"] = rsi(close, params.rsi_period)
    macd_frame = macd(close, params.macd_fast, params.macd_slow, params.macd_signal)
    out["macd"] = macd_frame["macd"]
    out["macd_signal"] = macd_frame["signal"]
    out["macd_hist"] = macd_frame["histogram"]
    out["atr"] = atr(out["high"], out["low"], close, params.atr_period)
    bands = bollinger_bands(close, params.bb_period, params.bb_std)
    out["bb_upper"] = bands["upper"]
    out["bb_middle"] = bands["middle"]
    out["bb_lower"] = bands["lower"]
    out["adx"] = adx(out["high"], out["low"], close, params.adx_period)
    return out


def evaluate(frame: pd.DataFrame, params: TechnicalParams | None = None) -> StrategyResult:
    """Evaluate ``frame`` and produce a directional :class:`StrategyResult`.

    Args:
        frame: OHLCV frame indexed by open time, oldest-first.
        params: Optional strategy parameters.

    Raises:
        ValueError: If there are fewer than :data:`_MIN_BARS` bars of history.
    """
    params = params or TechnicalParams()
    if len(frame) < _MIN_BARS:
        raise ValueError(f"Need at least {_MIN_BARS} bars to evaluate a signal, got {len(frame)}")

    enriched = compute_indicators(frame, params)
    latest = enriched.iloc[-1]
    previous = enriched.iloc[-2]
    reasons: list[str] = []

    ema_component = _trend_component(latest, reasons, params)
    macd_component = _macd_component(latest, previous, reasons)
    rsi_component = _rsi_component(latest, reasons)
    bb_component = _bollinger_component(latest, reasons)
    momentum_component = _momentum_component(latest, reasons)

    composite = (
        0.30 * ema_component
        + 0.25 * macd_component
        + 0.20 * rsi_component
        + 0.15 * bb_component
        + 0.10 * momentum_component
    )

    trend_strength = _trend_strength(latest.get("adx"))
    signal, confidence = signal_from_composite(composite, trend_strength, params)

    indicators = IndicatorSnapshot(
        rsi=_round(latest.get("rsi")),
        macd_histogram=_round(latest.get("macd_hist")),
        macd_cross=_macd_cross(latest, previous),
        ema_fast=_round(latest.get("ema_fast")),
        ema_slow=_round(latest.get("ema_slow")),
        ema_cross=_ema_cross(latest),
        atr=_round(latest.get("atr")),
        adx=_round(latest.get("adx")),
        bb_upper=_round(latest.get("bb_upper")),
        bb_lower=_round(latest.get("bb_lower")),
    )
    key_levels = _key_levels(enriched, params)

    if not reasons:
        reasons.append("No directional edge detected")

    return StrategyResult(
        signal=signal,
        confidence=confidence,
        price=float(latest["close"]),
        indicators=indicators,
        key_levels=key_levels,
        composite=round(composite, 4),
        trend_strength=round(trend_strength, 4),
        reasons=reasons,
    )


# ---------------------------------------------------------------------- #
# Component scoring
# ---------------------------------------------------------------------- #
def _trend_component(latest: pd.Series, reasons: list[str], params: TechnicalParams) -> float:
    fast, slow = latest.get("ema_fast"), latest.get("ema_slow")
    if pd.isna(fast) or pd.isna(slow):
        return 0.0
    if fast > slow:
        reasons.append(f"EMA{params.ema_fast} above EMA{params.ema_slow} (uptrend)")
        return 1.0
    if fast < slow:
        reasons.append(f"EMA{params.ema_fast} below EMA{params.ema_slow} (downtrend)")
        return -1.0
    return 0.0


def _macd_component(latest: pd.Series, previous: pd.Series, reasons: list[str]) -> float:
    hist = latest.get("macd_hist")
    prev_hist = previous.get("macd_hist")
    if pd.isna(hist):
        return 0.0
    score = 1.0 if hist > 0 else -1.0
    if not pd.isna(prev_hist) and hist > prev_hist:
        score += 0.3
    elif not pd.isna(prev_hist) and hist < prev_hist:
        score -= 0.3
    reasons.append(f"MACD histogram {'positive' if hist > 0 else 'negative'}")
    return max(-1.0, min(1.0, score))


def _rsi_component(latest: pd.Series, reasons: list[str]) -> float:
    value = latest.get("rsi")
    if pd.isna(value):
        return 0.0
    component = max(-1.0, min(1.0, (float(value) - 50.0) / 30.0))
    if value >= 70:
        reasons.append(f"RSI overbought ({value:.1f})")
    elif value <= 30:
        reasons.append(f"RSI oversold ({value:.1f})")
    return component


def _bollinger_component(latest: pd.Series, reasons: list[str]) -> float:
    close = latest.get("close")
    upper, lower, middle = latest.get("bb_upper"), latest.get("bb_lower"), latest.get("bb_middle")
    if pd.isna(upper) or pd.isna(lower) or pd.isna(close) or upper == lower:
        return 0.0
    position = (float(close) - float(lower)) / (float(upper) - float(lower))
    if position > 1.0:
        reasons.append("Price above upper Bollinger Band (overextended)")
        return -1.0
    if position < 0.0:
        reasons.append("Price below lower Bollinger Band (oversold)")
        return 1.0
    if pd.notna(middle):
        return max(
            -1.0, min(1.0, (float(close) - float(middle)) / (float(upper) - float(middle) or 1.0))
        )
    return 0.0


def _momentum_component(latest: pd.Series, reasons: list[str]) -> float:
    close, short_sma = latest.get("close"), latest.get("sma_short")
    if pd.isna(short_sma) or pd.isna(close):
        return 0.0
    return 1.0 if close > short_sma else -1.0


# ---------------------------------------------------------------------- #
# Aggregation helpers
# ---------------------------------------------------------------------- #
def _trend_strength(adx_value: float | None) -> float:
    if adx_value is None or pd.isna(adx_value):
        return 1.0
    return max(0.4, min(1.0, float(adx_value) / 40.0))


def signal_from_composite(
    composite: float, trend_strength: float, params: TechnicalParams
) -> tuple[Direction, float]:
    """Map a ``[-1, 1]`` composite score to a direction and confidence."""
    if abs(composite) < params.neutral_threshold:
        return Direction.NEUTRAL, 0.5
    signal = Direction.BULLISH if composite > 0 else Direction.BEARISH
    confidence = max(0.05, min(0.99, abs(composite) * trend_strength))
    return signal, round(confidence, 4)


def _key_levels(enriched: pd.DataFrame, params: TechnicalParams) -> KeyLevels:
    window = enriched.tail(params.level_lookback)
    return KeyLevels(
        support=_round(window["low"].min()),
        resistance=_round(window["high"].max()),
    )


def _macd_cross(latest: pd.Series, previous: pd.Series) -> str | None:
    if latest.get("macd_hist", 0) > 0 >= previous.get("macd_hist", 0):
        return "bullish_cross"
    if latest.get("macd_hist", 0) < 0 <= previous.get("macd_hist", 0):
        return "bearish_cross"
    return None


def _ema_cross(latest: pd.Series) -> str | None:
    fast, slow = latest.get("ema_fast"), latest.get("ema_slow")
    if pd.isna(fast) or pd.isna(slow):
        return None
    return "golden_cross" if fast > slow else "death_cross"


def _round(value: float | None, digits: int = 5) -> float | None:
    if value is None or pd.isna(value):
        return None
    return round(float(value), digits)
