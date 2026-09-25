"""Vectorised technical indicators implemented with pandas/NumPy.

These are pure-Python implementations so the system does not depend on the
TA-Lib C library. All functions accept a price ``Series`` (or OHLC frame) and
return pandas objects indexed identically to the input.

Conventions:
    * RSI/ATR/ADX use Wilder's smoothing.
    * Bollinger Bands use a population standard deviation (``ddof=0``).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

__all__ = [
    "adx",
    "atr",
    "bollinger_bands",
    "ema",
    "macd",
    "rsi",
    "sma",
    "stochastic",
]


def sma(series: pd.Series, period: int = 20) -> pd.Series:
    """Simple moving average."""
    _validate_period(period)
    return series.rolling(window=period, min_periods=period).mean()


def ema(series: pd.Series, period: int = 20) -> pd.Series:
    """Exponential moving average (``adjust=False``)."""
    _validate_period(period)
    return series.ewm(span=period, adjust=False, min_periods=period).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index using Wilder's smoothing."""
    _validate_period(period)
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss
    result = 100.0 - (100.0 / (1.0 + rs))
    result = result.where(avg_loss != 0.0, 100.0)
    return result.where(~((avg_loss == 0.0) & (avg_gain == 0.0)), 50.0)


def macd(
    series: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> pd.DataFrame:
    """Moving Average Convergence Divergence.

    Returns:
        Frame with ``macd``, ``signal`` and ``histogram`` columns.
    """
    _validate_period(fast)
    _validate_period(slow)
    _validate_period(signal)
    if fast >= slow:
        raise ValueError("fast period must be smaller than slow period")
    macd_line = ema(series, fast) - ema(series, slow)
    signal_line = macd_line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    return pd.DataFrame(
        {
            "macd": macd_line,
            "signal": signal_line,
            "histogram": macd_line - signal_line,
        },
        index=series.index,
    )


def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    """True Range: max of high-low, |high-prev close|, |low-prev close|."""
    prev_close = close.shift(1)
    ranges = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    )
    return ranges.max(axis=1)


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """Average True Range using Wilder's smoothing."""
    _validate_period(period)
    tr = true_range(high, low, close)
    return tr.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()


def bollinger_bands(series: pd.Series, period: int = 20, num_std: float = 2.0) -> pd.DataFrame:
    """Bollinger Bands.

    Returns:
        Frame with ``middle``, ``upper`` and ``lower`` columns.
    """
    _validate_period(period)
    middle = sma(series, period)
    std = series.rolling(window=period, min_periods=period).std(ddof=0)
    return pd.DataFrame(
        {
            "middle": middle,
            "upper": middle + num_std * std,
            "lower": middle - num_std * std,
        },
        index=series.index,
    )


def stochastic(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    k_period: int = 14,
    d_period: int = 3,
) -> pd.DataFrame:
    """Stochastic oscillator (%K / %D).

    Returns:
        Frame with ``k`` and ``d`` columns.
    """
    _validate_period(k_period)
    _validate_period(d_period)
    lowest = low.rolling(window=k_period, min_periods=k_period).min()
    highest = high.rolling(window=k_period, min_periods=k_period).max()
    span = (highest - lowest).replace(0.0, np.nan)
    k = 100.0 * (close - lowest) / span
    return pd.DataFrame({"k": k, "d": k.rolling(window=d_period, min_periods=d_period).mean()})


def adx(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14,
) -> pd.Series:
    """Average Directional Index (Wilder)."""
    _validate_period(period)
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = pd.Series(
        np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=high.index
    )
    minus_dm = pd.Series(
        np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=high.index
    )
    tr = true_range(high, low, close)
    atr_values = tr.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    plus_di = (
        100.0
        * plus_dm.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
        / atr_values.replace(0.0, np.nan)
    )
    minus_di = (
        100.0
        * minus_dm.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
        / atr_values.replace(0.0, np.nan)
    )
    denominator = (plus_di + minus_di).replace(0.0, np.nan)
    dx = 100.0 * (plus_di - minus_di).abs() / denominator
    return dx.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()


def _validate_period(period: int) -> None:
    if period < 2:
        raise ValueError(f"period must be at least 2, got {period}")
