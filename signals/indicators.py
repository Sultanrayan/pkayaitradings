"""Pure technical indicators.

Every function here is a pure transformation of its inputs: no module state, no
I/O, no clock reads. That is not stylistic — it is what makes the no-repaint
guarantee checkable. A function that cannot see anything except its arguments
cannot accidentally consult a future bar.

Look-ahead policy
-----------------
Two constructs in this file look like look-ahead but are not, and both are
commented at their definitions:

* **Confirmed swings.** A swing high at bar ``i`` is only *known* once bar
  ``i + lookback`` has printed a lower high. Using it at bar ``i`` would be
  look-ahead. :func:`confirmed_swing_highs` therefore reports the pivot and the
  bar at which it became knowable, and the caller evaluates it from that bar
  onward.

* **Supertrend.** The band flips based on the prior bar's close only, never the
  current bar's, so a bar's own value is final once the bar closes.

Nothing in this module calls ``shift`` with a negative argument.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

__all__ = [
    "adx",
    "atr",
    "bb_width",
    "bollinger_bands",
    "confirmed_swing_highs",
    "confirmed_swing_lows",
    "ema",
    "macd",
    "rsi",
    "sma",
    "stochastic",
    "supertrend",
    "true_range",
    "volume_ma",
]


def _validate_period(period: int) -> None:
    """Reject a nonsensical lookback.

    Raises:
        ValueError: If ``period`` is below 2.
    """
    if period < 2:
        raise ValueError(f"period must be at least 2, got {period}")


def _as_float(series: pd.Series) -> pd.Series:
    """Coerce to float, keeping the index and the NaN positions.

    Indicators must not raise on a NaN input; a NaN input yields a NaN output at
    that position, which the layers translate into "not evaluable".
    """
    return pd.to_numeric(series, errors="coerce").astype("float64")


def sma(series: pd.Series, period: int = 20) -> pd.Series:
    """Simple moving average.

    Args:
        series: Input values.
        period: Window length.

    Returns:
        Series of the same length and index; the first ``period - 1`` entries
        are NaN because the window is not yet full.
    """
    _validate_period(period)
    return _as_float(series).rolling(window=period, min_periods=period).mean()


def ema(series: pd.Series, period: int = 20) -> pd.Series:
    """Exponential moving average with ``adjust=False``.

    ``adjust=False`` makes the value depend only on the current and previous
    inputs, which is what a live bar-by-bar calculation would produce. The
    ``adjust=True`` variant rescales the whole history and therefore disagrees
    with an incremental feed; that difference is why it is not used.
    """
    _validate_period(period)
    return _as_float(series).ewm(span=period, adjust=False, min_periods=period).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index with Wilder's smoothing.

    Returns:
        Series in ``[0, 100]``. A window with no losses reads 100, a window with
        no moves reads 50, and the first ``period`` entries are NaN.
    """
    _validate_period(period)
    values = _as_float(series)
    delta = values.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss
    out = 100.0 - (100.0 / (1.0 + rs))
    # avg_loss == 0 means an unbroken run of non-declines. avg_gain == 0 as well
    # means a flat window, which is not bullish and must not read as 100.
    out = out.where(avg_loss != 0.0, 100.0)
    out = out.where(~((avg_loss == 0.0) & (avg_gain == 0.0)), 50.0)
    out.iloc[:1] = np.nan
    return out


def macd(
    series: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> pd.DataFrame:
    """Moving Average Convergence Divergence.

    Returns:
        Frame with ``macd``, ``signal`` and ``histogram`` columns, all indexed
        identically to the input.

    Raises:
        ValueError: If ``fast`` is not smaller than ``slow``.
    """
    _validate_period(fast)
    _validate_period(slow)
    _validate_period(signal)
    if fast >= slow:
        raise ValueError(f"fast ({fast}) must be smaller than slow ({slow})")
    values = _as_float(series)
    macd_line = ema(values, fast) - ema(values, slow)
    signal_line = macd_line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    return pd.DataFrame(
        {
            "macd": macd_line,
            "signal": signal_line,
            "histogram": macd_line - signal_line,
        },
        index=values.index,
    )


def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    """Wilder's True Range.

    Uses the *previous* bar's close only. The first entry has no previous close
    and is NaN rather than ``high - low``, which would understate the very first
    bar's range.
    """
    high_f = _as_float(high)
    low_f = _as_float(low)
    close_f = _as_float(close)
    prev_close = close_f.shift(1)
    ranges = pd.concat(
        [high_f - low_f, (high_f - prev_close).abs(), (low_f - prev_close).abs()],
        axis=1,
    )
    out = ranges.max(axis=1)
    out.iloc[:1] = np.nan
    return out


def atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14,
) -> pd.Series:
    """Average True Range with Wilder's smoothing."""
    _validate_period(period)
    return true_range(high, low, close).ewm(
        alpha=1.0 / period, adjust=False, min_periods=period
    ).mean()


def bollinger_bands(
    series: pd.Series,
    period: int = 20,
    num_std: float = 2.0,
) -> pd.DataFrame:
    """Bollinger Bands with a population standard deviation (``ddof=0``).

    ``ddof=0`` matches the convention used elsewhere in this project; the sample
    deviation would shift the bands very slightly on short windows.
    """
    _validate_period(period)
    values = _as_float(series)
    middle = sma(values, period)
    std = values.rolling(window=period, min_periods=period).std(ddof=0)
    return pd.DataFrame(
        {"middle": middle, "upper": middle + num_std * std, "lower": middle - num_std * std},
        index=values.index,
    )


def bb_width(close: pd.Series, period: int = 20, num_std: float = 2.0) -> pd.Series:
    """Bollinger Band width as a fraction of the middle band.

    A squeeze is a width in the lowest part of its recent distribution, so this
    is what the volatility layer compares against a rolling quantile.
    """
    bands = bollinger_bands(close, period, num_std)
    middle = bands["middle"].replace(0.0, np.nan)
    return (bands["upper"] - bands["lower"]) / middle


def stochastic(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    k_period: int = 14,
    d_period: int = 3,
) -> pd.DataFrame:
    """Stochastic oscillator (``%K`` and its ``%D`` smoothing).

    Returns:
        Frame with ``k`` and ``d`` columns. A window where the high equals the
        low would divide by zero; those entries are NaN rather than an arbitrary
        constant.
    """
    _validate_period(k_period)
    _validate_period(d_period)
    high_f = _as_float(high)
    low_f = _as_float(low)
    close_f = _as_float(close)
    lowest = low_f.rolling(window=k_period, min_periods=k_period).min()
    highest = high_f.rolling(window=k_period, min_periods=k_period).max()
    span = (highest - lowest).replace(0.0, np.nan)
    k = 100.0 * (close_f - lowest) / span
    return pd.DataFrame(
        {"k": k, "d": k.rolling(window=d_period, min_periods=d_period).mean()},
        index=close_f.index,
    )


def adx(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14,
) -> pd.Series:
    """Average Directional Index with Wilder's smoothing.

    Returns:
        Series in ``[0, 100]``, NaN until the smoothing window fills.
    """
    _validate_period(period)
    high_f = _as_float(high)
    low_f = _as_float(low)
    close_f = _as_float(close)

    up_move = high_f.diff()
    down_move = -low_f.diff()
    plus_dm = pd.Series(
        np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=high_f.index
    )
    minus_dm = pd.Series(
        np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=high_f.index
    )

    tr = true_range(high_f, low_f, close_f)
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


def volume_ma(volume: pd.Series, period: int = 20) -> pd.Series:
    """Moving average of volume."""
    _validate_period(period)
    return sma(volume, period)


def supertrend(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 10,
    multiplier: float = 3.0,
) -> pd.DataFrame:
    """Supertrend.

    The band flip on bar ``i`` reads bar ``i - 1``'s close, never bar ``i``'s, so
    a bar's Supertrend value is final the moment the bar closes and does not move
    afterwards.

    Returns:
        Frame with ``line`` (the active band) and ``direction`` (``1`` uptrend,
        ``-1`` downtrend). Both are NaN until the ATR seed fills.
    """
    _validate_period(period)
    if multiplier <= 0.0:
        raise ValueError(f"multiplier must be positive, got {multiplier}")

    high_f = _as_float(high)
    low_f = _as_float(low)
    close_f = _as_float(close)
    atr_values = atr(high_f, low_f, close_f, period)

    # Bands from the midpoint and ATR. Both series are indexed identically, so the
    # arithmetic is positional and correct.
    hl2 = (high_f + low_f) / 2.0
    upper = hl2 + multiplier * atr_values
    lower = hl2 - multiplier * atr_values

    n = len(close_f)
    line = np.full(n, np.nan)
    # `direction` is what this function returns; `trend` is the running state that
    # produces it. Both start as NaN so a bar before the ATR seed reports an
    # undefined trend rather than a third "no trend" state that cannot exist.
    direction = np.full(n, np.nan)
    close_values = close_f.to_numpy()
    upper_values = upper.to_numpy()
    lower_values = lower.to_numpy()
    atr_array = atr_values.to_numpy()

    final_upper = np.full(n, np.nan)
    final_lower = np.full(n, np.nan)
    trend = np.full(n, np.nan)

    started = False
    for i in range(n):
        if np.isnan(atr_array[i]):
            # Carry nothing forward while the ATR is still seeding; the bands are
            # undefined, so the indicator is undefined rather than guessed.
            continue
        if not started:
            final_upper[i] = upper_values[i]
            final_lower[i] = lower_values[i]
            trend[i] = 1.0
            started = True
        else:
            prev_close = close_values[i - 1]
            # The band only ratchets in the favourable direction while the trend
            # holds; it is reset when price breaks through it.
            final_upper[i] = (
                upper_values[i] if (upper_values[i] < final_upper[i - 1] or prev_close > final_upper[i - 1])
                else final_upper[i - 1]
            )
            final_lower[i] = (
                lower_values[i] if (lower_values[i] > final_lower[i - 1] or prev_close < final_lower[i - 1])
                else final_lower[i - 1]
            )
            if close_values[i] > final_upper[i]:
                trend[i] = 1.0
            elif close_values[i] < final_lower[i]:
                trend[i] = -1.0
            else:
                trend[i] = trend[i - 1]

        direction[i] = trend[i]
        line[i] = final_lower[i] if trend[i] > 0 else final_upper[i]

    return pd.DataFrame(
        {
            "line": pd.Series(line, index=close_f.index),
            "direction": pd.Series(direction, index=close_f.index),
        }
    )


def confirmed_swing_highs(
    high: pd.Series,
    lookback: int = 5,
) -> pd.DataFrame:
    """Swing highs with the bar at which each became knowable.

    A bar is a swing high when its high is the strict maximum of the
    ``2 * lookback + 1`` bars centred on it. That centre can only be confirmed
    once the following ``lookback`` bars have printed, so the pivot at position
    ``p`` is reported against position ``p + lookback``.

    Returning the confirmation position is the whole point: a caller that scores
    support/resistance at bar ``i`` from the pivot at ``i - lookback`` has not
    looked ahead, while a caller that scores it from the pivot at ``i +
    lookback`` has.

    Returns:
        Frame with ``pivot_pos``, ``confirm_pos`` and ``price`` columns. It is
        shorter than the input — one row per confirmed pivot.
    """
    _validate_period(lookback)
    high_f = _as_float(high)
    # max of the `lookback` bars BEFORE this one, and of the `lookback` bars AFTER
    # it. The forward window is a *computation* convenience only: this pivot is
    # never handed to a caller until `confirm_pos`, which is exactly `lookback`
    # bars later. Consuming the right-hand window earlier than that is what would
    # constitute look-ahead, and :func:`score_support_resistance` does not.
    left = high_f.rolling(lookback, min_periods=lookback).max().shift(1)
    # Reversing, rolling, and reversing back yields each bar's max over the next
    # `lookback` bars; shifting by -1 drops that bar from its own window.
    right = high_f[::-1].rolling(lookback, min_periods=lookback).max()[::-1].shift(-1)
    # Strict comparison on both sides. `>=` would mark every bar of a flat series
    # as a pivot, which is nonsense: a level that never moved is not a swing.
    is_pivot = high_f.gt(left) & high_f.gt(right)
    positions = np.flatnonzero(is_pivot.to_numpy())
    if positions.size == 0:
        return pd.DataFrame(
            {
                "pivot_pos": pd.Series(dtype="int64"),
                "confirm_pos": pd.Series(dtype="int64"),
                "price": pd.Series(dtype="float64"),
            }
        )
    confirm = positions + lookback
    keep = confirm < len(high_f)
    return pd.DataFrame(
        {
            "pivot_pos": positions[keep],
            "confirm_pos": confirm[keep],
            "price": high_f.to_numpy()[positions[keep]],
        }
    )


def confirmed_swing_lows(
    low: pd.Series,
    lookback: int = 5,
) -> pd.DataFrame:
    """Swing lows with the bar at which each became knowable.

    Mirror of :func:`confirmed_swing_highs`. See that function for why the
    confirmation position is returned separately.
    """
    _validate_period(lookback)
    low_f = _as_float(low)
    # See confirmed_swing_highs for why the forward window is computed here but
    # only ever exposed from the confirmation bar onward.
    left = low_f.rolling(lookback, min_periods=lookback).min().shift(1)
    right = low_f[::-1].rolling(lookback, min_periods=lookback).min()[::-1].shift(-1)
    is_pivot = low_f.lt(left) & low_f.lt(right)
    positions = np.flatnonzero(is_pivot.to_numpy())
    if positions.size == 0:
        return pd.DataFrame(
            {
                "pivot_pos": pd.Series(dtype="int64"),
                "confirm_pos": pd.Series(dtype="int64"),
                "price": pd.Series(dtype="float64"),
            }
        )
    confirm = positions + lookback
    keep = confirm < len(low_f)
    return pd.DataFrame(
        {
            "pivot_pos": positions[keep],
            "confirm_pos": confirm[keep],
            "price": low_f.to_numpy()[positions[keep]],
        }
    )
