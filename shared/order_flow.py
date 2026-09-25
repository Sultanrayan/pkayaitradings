"""Order-flow imbalance analyzer (backend-v2, Problem 7).

biquote only exposes OHLCV candles, so the analyzer derives absorption proxies
from candle structure and tick volume:

* **cumulative delta** — up-bar volume minus down-bar volume over a window;
* **divergence** — whether price and the delta oscillator move together or
  apart over the recent lookback;
* **exhaustion** — long upper/lower wicks signalling absorption of buying or
  selling pressure.

Each component produces a ``[-1, 1]`` reading (positive = bullish absorption)
and they are blended into a single score that maps to a
:class:`~shared.schemas.enums.Direction` verdict.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from shared.schemas.enums import Direction

_DELTA_WEIGHT = 0.40
_DIVERGENCE_WEIGHT = 0.35
_EXHAUSTION_WEIGHT = 0.25
_DIRECTION_THRESHOLD = 0.20
_WICK_RATIO = 0.5


@dataclass(frozen=True)
class OrderFlowSignal:
    """Directional absorption verdict from the order-flow analyzer."""

    direction: Direction
    score: float
    delta: float
    divergence: float
    exhaustion: float
    reasons: tuple[str, ...] = ()


def analyze_order_flow(
    frame: pd.DataFrame,
    *,
    delta_window: int = 20,
    divergence_lookback: int = 30,
) -> OrderFlowSignal:
    """Analyse an OHLCV frame (oldest-first) for absorption signals.

    ``tick_volume`` is optional; when absent the analyzer falls back to a
    volume-neutral reading so the delta component stays undefined (0.0).
    """
    required = {"open", "high", "low", "close"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"OHLC frame is missing columns: {sorted(missing)}")

    reasons: list[str] = []
    delta = _cumulative_delta(frame, delta_window)
    divergence = _price_delta_divergence(frame, divergence_lookback)
    exhaustion = _wick_exhaustion(frame)

    if abs(delta) >= 0.10:
        reasons.append(f"cumulative delta {delta:+.2f} over {delta_window} bars")
    if abs(divergence) >= 0.10:
        reasons.append(f"price/delta {'divergence' if divergence > 0 else 'convergence'} {divergence:+.2f}")
    if abs(exhaustion) >= 0.10:
        reasons.append(f"{'buying' if exhaustion > 0 else 'selling'} absorption via wicks {exhaustion:+.2f}")

    score = _DELTA_WEIGHT * delta + _DIVERGENCE_WEIGHT * divergence + _EXHAUSTION_WEIGHT * exhaustion
    score = float(max(-1.0, min(1.0, score)))

    if score >= _DIRECTION_THRESHOLD:
        direction = Direction.BULLISH
    elif score <= -_DIRECTION_THRESHOLD:
        direction = Direction.BEARISH
    else:
        direction = Direction.NEUTRAL

    if not reasons:
        reasons.append("No order-flow absorption detected")

    return OrderFlowSignal(
        direction=direction,
        score=round(score, 4),
        delta=round(delta, 4),
        divergence=round(divergence, 4),
        exhaustion=round(exhaustion, 4),
        reasons=tuple(reasons),
    )


def _cumulative_delta(frame: pd.DataFrame, window: int) -> float:
    """Normalised net buy volume over ``window`` bars in ``[-1, 1]``."""
    if "tick_volume" not in frame.columns:
        return 0.0
    volume = frame["tick_volume"].fillna(0.0).astype(float)
    up = (frame["close"] >= frame["open"]).astype(float)
    signed = (2.0 * up - 1.0) * volume
    windowed = signed.tail(window)
    total = windowed.abs().sum()
    if total <= 0:
        return 0.0
    return float(windowed.sum() / total)


def _price_delta_divergence(frame: pd.DataFrame, lookback: int) -> float:
    """Whether price and net-flow momentum have separated over the lookback."""
    window = frame.tail(lookback)
    if len(window) < 3 or "tick_volume" not in frame.columns:
        return 0.0
    close = window["close"].to_numpy()
    up = (window["close"] >= window["open"]).astype(float).to_numpy()
    volume = window["tick_volume"].fillna(0.0).astype(float).to_numpy()
    flow = (2.0 * up - 1.0) * volume
    flow = np.cumsum(flow)

    price_slope = _linear_slope(np.arange(len(close)), close)
    flow_slope = _linear_slope(np.arange(len(flow)), flow)
    scale = np.std(close) or 1.0
    price_trend = price_slope / scale
    flow_trend = flow_slope / (np.sum(np.abs(volume)) or 1.0)

    divergence = flow_trend - price_trend
    return float(max(-1.0, min(1.0, divergence)))


def _wick_exhaustion(frame: pd.DataFrame) -> float:
    """Net absorption sign derived from recent candle wicks."""
    recent = frame.tail(5)
    if len(recent) < 3:
        return 0.0
    upper = recent["high"] - recent[["open", "close"]].max(axis=1)
    lower = recent[["open", "close"]].min(axis=1) - recent["low"]
    ranges = (recent["high"] - recent["low"]).replace(0.0, np.nan)
    upper_ratio = (upper / ranges).fillna(0.0).mean()
    lower_ratio = (lower / ranges).fillna(0.0).mean()
    exhaustion = (lower_ratio - upper_ratio) / _WICK_RATIO
    return float(max(-1.0, min(1.0, exhaustion)))


def _linear_slope(x: np.ndarray, y: np.ndarray) -> float:
    if len(x) < 2 or np.all(x == x[0]):
        return 0.0
    return float(np.polyfit(x, y, 1)[0])
