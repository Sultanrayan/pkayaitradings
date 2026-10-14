"""Indicator layer for the Telegram bot — pure functions, no state.

Reuses :mod:`signals.indicators` where the definition already matches, rather
than maintaining a second copy that would drift. What is added here is what the
bot's seven layers need and the signal engine does not provide: OBV, MFI,
Keltner Channels, pivot points, and Fibonacci levels.

Look-ahead policy is identical to the engine's: every function is streaming, so a
value at bar ``i`` depends only on bars ``0..i``. The one exception is swing
detection, which is inherently defined by following bars and is handled by
confirming a pivot before it is used.
"""

from __future__ import annotations

from typing import cast

import numpy as np
import pandas as pd

from signals.indicators import (
    adx,
    atr,
    bollinger_bands,
    confirmed_swing_highs,
    confirmed_swing_lows,
    ema,
    macd,
    rsi,
    sma,
    stochastic,
    supertrend,
)

# The names above are re-exported so callers write ``ind.macd(...)`` rather than
# reaching into ``signals.indicators``. They are listed here explicitly: without
# this the module looked like it had no MACD at all, since a name absent from
# ``__all__`` is not re-exported and ``ind.macd`` raised AttributeError.
__all__ = [
    "adx",
    "atr",
    "bollinger_bands",
    "ema",
    "fibo_levels",
    "keltner_channels",
    "macd",
    "mfi",
    "obv",
    "pivot_points",
    "rsi",
    "sma",
    "stochastic",
    "supertrend",
    "swing_levels",
]


def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    """On-Balance Volume.

    Cumulative signed volume: volume is added on an up close and subtracted on a
    down close. A flat close contributes nothing, which is the standard treatment
    — attributing a flat bar to either side would bias the cumulative line.

    Args:
        close: Close prices.
        volume: Volume for the same bars.

    Returns:
        Series aligned to ``close``, starting at 0 for the first bar.
    """
    close = pd.to_numeric(close, errors="coerce")
    volume = pd.to_numeric(volume, errors="coerce")
    direction = np.sign(close.diff().fillna(0.0))
    signed = direction * volume.fillna(0.0)
    return cast(pd.Series, signed.cumsum())


def mfi(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series, period: int = 14) -> pd.Series:
    """Money Flow Index.

    RSI weighted by volume: typical price ``(high + low + close) / 3``, split into
    positive and negative money flow, compared over ``period`` bars.

    Args:
        high: High prices.
        low: Low prices.
        close: Close prices.
        volume: Volume.
        period: Lookback.

    Returns:
        Series in ``[0, 100]``, NaN until the window fills. A window with no
        negative flow reads 100; one with no positive flow reads 0.
    """
    if period < 2:
        raise ValueError(f"period must be at least 2, got {period}")
    high = pd.to_numeric(high, errors="coerce")
    low = pd.to_numeric(low, errors="coerce")
    close = pd.to_numeric(close, errors="coerce")
    volume = pd.to_numeric(volume, errors="coerce")

    typical = (high + low + close) / 3.0
    flow = typical * volume.fillna(0.0)
    delta = typical.diff()

    positive = flow.where(delta > 0.0, 0.0).rolling(period, min_periods=period).sum()
    negative = flow.where(delta < 0.0, 0.0).rolling(period, min_periods=period).sum()

    ratio = positive / negative.replace(0.0, np.nan)
    result = 100.0 - (100.0 / (1.0 + ratio))
    # No negative flow means every period was up: 100, not a division artefact.
    result = result.where(negative != 0.0, 100.0)
    result = result.where(~((negative == 0.0) & (positive == 0.0)), 50.0)
    result.iloc[:1] = np.nan
    return result


def keltner_channels(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    *,
    period: int = 20,
    atr_period: int = 10,
    multiplier: float = 1.5,
) -> pd.DataFrame:
    """Keltner Channels: an EMA centreline with ATR-based bands.

    Args:
        high: High prices.
        low: Low prices.
        close: Close prices.
        period: EMA period for the centreline.
        atr_period: ATR lookback.
        multiplier: Band width in ATR multiples.

    Returns:
        Frame with ``middle``, ``upper`` and ``lower``.
    """
    if multiplier <= 0.0:
        raise ValueError(f"multiplier must be positive, got {multiplier}")
    middle = ema(close, period)
    band = atr(high, low, close, atr_period) * multiplier
    return pd.DataFrame(
        {"middle": middle, "upper": middle + band, "lower": middle - band},
        index=close.index,
    )


def pivot_points(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.DataFrame:
    """Classic pivot points from the **previous** bar.

    Uses ``shift(1)`` on every input, so a bar's pivots depend only on the bar
    before it. This is the form that can be drawn live without repainting — the
    "current bar" pivots computed from the bar's own H/L/C would change until the
    bar closed.

    Returns:
        Frame with ``pivot``, ``r1``, ``r2``, ``r3``, ``s1``, ``s2``, ``s3``.
    """
    high = pd.to_numeric(high, errors="coerce")
    low = pd.to_numeric(low, errors="coerce")
    close = pd.to_numeric(close, errors="coerce")

    prev_high = high.shift(1)
    prev_low = low.shift(1)
    prev_close = close.shift(1)

    span = prev_high - prev_low
    pivot = (prev_high + prev_low + prev_close) / 3.0
    r1 = 2.0 * pivot - prev_low
    s1 = 2.0 * pivot - prev_high
    r2 = pivot + span
    s2 = pivot - span
    r3 = prev_high + 2.0 * (pivot - prev_low)
    s3 = prev_low - 2.0 * (prev_high - pivot)

    return pd.DataFrame(
        {
            "pivot": pivot,
            "r1": r1,
            "r2": r2,
            "r3": r3,
            "s1": s1,
            "s2": s2,
            "s3": s3,
        },
        index=close.index,
    )


def swing_levels(
    high: pd.Series, low: pd.Series, *, lookback: int = 10
) -> pd.DataFrame:
    """Confirmed swing highs and lows, broadcast from each pivot's confirm bar.

    A swing high at bar ``p`` is only knowable at ``p + lookback``. The value is
    therefore written from the confirmation bar onward, which is what makes the
    levels safe to consume bar by bar.

    Returns:
        Frame with ``high_pos``, ``high_price`` and the low-side equivalents,
        broadcast across all bars.
    """
    highs = confirmed_swing_highs(high, lookback)
    lows = confirmed_swing_lows(low, lookback)
    n = len(high)

    def _broadcast(pivots: pd.DataFrame, column: str) -> np.ndarray:
        values = np.full(n, np.nan)
        if pivots.empty:
            return values
        for confirm, value in zip(
            pivots["confirm_pos"].to_numpy(dtype="float64"),
            pivots[column].to_numpy(dtype="float64"),
            strict=True,
        ):
            index = int(confirm)
            if 0 <= index < n:
                values[index:] = value
        return values

    return pd.DataFrame(
        {
            "high_price": _broadcast(highs, "price"),
            "high_pos": _broadcast(highs, "pivot_pos"),
            "low_price": _broadcast(lows, "price"),
            "low_pos": _broadcast(lows, "pivot_pos"),
        },
        index=high.index,
    )


def fibo_levels(
    high: pd.Series, low: pd.Series, *, lookback: int = 50
) -> pd.DataFrame:
    """Fibonacci retracement levels from a confirmed swing range.

    The range is taken from the **trailing** ``lookback`` bars ending at the
    current bar, so it is computable at the bar rather than requiring a future
    swing to be identified first. That trades "anchored to a confirmed swing" for
    "anchored to the recent range" — the latter is live-safe and the former is
    not, so the latter is what a non-repainting bot needs.

    Returns:
        Frame with ``fib_236``, ``fib_382``, ``fib_500``, ``fib_618``, ``fib_786``
        and the ``range_high`` / ``range_low`` they derive from.
    """
    if lookback < 2:
        raise ValueError(f"lookback must be at least 2, got {lookback}")
    high = pd.to_numeric(high, errors="coerce")
    low = pd.to_numeric(low, errors="coerce")

    range_high = high.rolling(lookback, min_periods=lookback).max()
    range_low = low.rolling(lookback, min_periods=lookback).min()
    span = range_high - range_low

    def _level(ratio: float) -> pd.Series:
        # Retracement is measured down from the high.
        return range_high - ratio * span

    return pd.DataFrame(
        {
            "range_high": range_high,
            "range_low": range_low,
            "fib_236": _level(0.236),
            "fib_382": _level(0.382),
            "fib_500": _level(0.500),
            "fib_618": _level(0.618),
            "fib_786": _level(0.786),
        },
        index=high.index,
    )
