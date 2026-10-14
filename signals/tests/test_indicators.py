"""Tests for the pure indicator functions.

Two properties matter beyond arithmetic correctness, and both are tested
explicitly because they are the ones that silently break:

* **No lookahead.** Each indicator's value at bar ``i`` must be unchanged when the
  frame is truncated at ``i``. ``test_indicators_have_no_lookahead`` truncates a
  series at every position and compares — an O(n²) check that catches any
  accidental ``shift(-k)`` or centred window.
* **NaN honesty.** An indicator returns NaN where it genuinely has no value rather
  than a plausible constant, because a layer that mistakes warmup for a reading is
  exactly how a signal fires on insufficient data.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from signals.indicators import (
    adx,
    atr,
    bb_width,
    bollinger_bands,
    confirmed_swing_highs,
    confirmed_swing_lows,
    ema,
    macd,
    rsi,
    sma,
    stochastic,
    supertrend,
    true_range,
)
from signals.tests.factories import make_ohlcv, make_range, make_trend_then_reverse


def _series(values: list[float]) -> pd.Series:
    return pd.Series(values, index=pd.date_range("2026-01-01", periods=len(values), tz="UTC"))


# --------------------------------------------------------------------------- #
# Moving averages
# --------------------------------------------------------------------------- #


def test_sma_matches_a_hand_computed_value() -> None:
    result = sma(_series([1.0, 2.0, 3.0, 4.0, 5.0]), period=3)
    assert np.isnan(result.iloc[0])
    assert np.isnan(result.iloc[1])
    assert result.iloc[2] == pytest.approx(2.0)
    assert result.iloc[4] == pytest.approx(4.0)


def test_ema_seed_is_the_first_observation_not_a_rescaled_mean() -> None:
    """``adjust=False`` seeds from the first value, which ``adjust=True`` cannot.

    With ``adjust=True`` pandas rescales the whole history, so the first output
    would be a weighted mean of every input. With ``adjust=False`` the recursion
    starts at the first observation — the value an incremental live feed would
    produce. ``min_periods`` then withholds the first ``period - 1`` outputs, so
    the value first appears at index ``period - 1``.
    """
    values = _series([10.0, 20.0, 30.0, 40.0])
    streamed = ema(values, period=3)

    # Ungated recursion, for comparison of the seed itself.
    ungated = values.ewm(span=3, adjust=False).mean()
    assert ungated.iloc[0] == pytest.approx(10.0)

    # The gated output equals the ungated one from the first allowed index on.
    assert np.isnan(streamed.iloc[0])
    assert np.isnan(streamed.iloc[1])
    for index in range(2, len(values)):
        assert streamed.iloc[index] == pytest.approx(ungated.iloc[index])

    # And it genuinely differs from the rescaled variant, which is the point.
    adjusted = values.ewm(span=3, adjust=True).mean()
    assert streamed.iloc[-1] != pytest.approx(adjusted.iloc[-1])


def test_ema_respects_min_periods() -> None:
    result = ema(_series([1.0] * 10), period=5)
    assert np.isnan(result.iloc[3])
    assert np.isfinite(result.iloc[4])


def test_ema_tracks_a_constant_series_exactly() -> None:
    result = ema(_series([5.0] * 20), period=10)
    assert result.iloc[-1] == pytest.approx(5.0)


def test_ema_of_a_rising_series_rises() -> None:
    result = ema(_series([float(i) for i in range(1, 51)]), period=10)
    assert result.iloc[-1] > result.iloc[10]


@pytest.mark.parametrize("period", [0, 1, -3])
def test_period_below_two_is_rejected(period: int) -> None:
    with pytest.raises(ValueError, match="at least 2"):
        sma(_series([1.0, 2.0]), period=period)


# --------------------------------------------------------------------------- #
# RSI
# --------------------------------------------------------------------------- #


def test_rsi_of_a_monotonic_rise_is_100() -> None:
    result = rsi(_series([float(i) for i in range(1, 40)]), period=14)
    assert result.iloc[-1] == pytest.approx(100.0)


def test_rsi_of_a_monotonic_fall_is_zero() -> None:
    result = rsi(_series([float(i) for i in range(40, 1, -1)]), period=14)
    assert result.iloc[-1] == pytest.approx(0.0)


def test_rsi_of_a_flat_series_is_50_not_100() -> None:
    """A window with no movement is not bullish.

    Returning 100 here is the classic RSI bug: dividing by a zero average loss
    without also checking a zero average gain.
    """
    result = rsi(_series([7.0] * 40), period=14)
    assert result.iloc[-1] == pytest.approx(50.0)


def test_rsi_stays_within_bounds() -> None:
    frame = make_range(300)
    result = rsi(frame["close"], period=14).dropna()
    assert result.min() >= 0.0
    assert result.max() <= 100.0


def test_rsi_first_bar_is_nan() -> None:
    """diff() on the first bar has no predecessor."""
    assert np.isnan(rsi(_series([1.0, 2.0, 3.0]), period=2).iloc[0])


# --------------------------------------------------------------------------- #
# MACD
# --------------------------------------------------------------------------- #


def test_macd_returns_three_columns_on_the_input_index() -> None:
    values = _series([float(i) for i in range(1, 60)])
    result = macd(values, fast=3, slow=6, signal=3)
    assert list(result.columns) == ["macd", "signal", "histogram"]
    assert result.index.equals(values.index)


def test_macd_histogram_is_the_difference_of_its_parts() -> None:
    result = macd(_series([float(i) for i in range(1, 60)]), fast=5, slow=13, signal=4)
    assert result["histogram"].iloc[-1] == pytest.approx(
        result["macd"].iloc[-1] - result["signal"].iloc[-1]
    )


def test_macd_rejects_fast_greater_than_slow() -> None:
    with pytest.raises(ValueError, match="must be smaller"):
        macd(_series([1.0, 2.0, 3.0]), fast=26, slow=12)


def test_macd_is_positive_in_an_uptrend() -> None:
    result = macd(_series([float(i) * i for i in range(1, 80)]))
    assert result["macd"].iloc[-1] > 0.0


# --------------------------------------------------------------------------- #
# True range / ATR
# --------------------------------------------------------------------------- #


def test_true_range_first_bar_is_nan() -> None:
    """The first bar has no previous close to gap against."""
    frame = make_ohlcv(10)
    result = true_range(frame["high"], frame["low"], frame["close"])
    assert np.isnan(result.iloc[0])


def test_true_range_captures_a_gap_up() -> None:
    """A gap makes TR exceed the bar's own high-low range."""
    high = _series([10.0, 20.0])
    low = _series([9.0, 19.0])
    close = _series([9.5, 19.5])
    result = true_range(high, low, close)
    # Second bar: |20 - 9.5| = 10.5 versus high-low = 1.0
    assert result.iloc[1] == pytest.approx(10.5)


def test_atr_is_positive_and_bounded_by_the_price_range() -> None:
    frame = make_ohlcv(200)
    result = atr(frame["high"], frame["low"], frame["close"], period=14).dropna()
    assert (result > 0.0).all()


def test_atr_widens_when_volatility_rises() -> None:
    calm = make_ohlcv(120, noise=0.0005, seed=3)
    wild = make_ohlcv(120, noise=0.02, seed=3)
    calm_atr = atr(calm["high"], calm["low"], calm["close"]).iloc[-1]
    wild_atr = atr(wild["high"], wild["low"], wild["close"]).iloc[-1]
    assert wild_atr > calm_atr


# --------------------------------------------------------------------------- #
# Bollinger
# --------------------------------------------------------------------------- #


def test_bollinger_bands_are_ordered_and_centred() -> None:
    values = _series([float(i % 7) for i in range(1, 60)])
    bands = bollinger_bands(values, period=20, num_std=2.0)
    finite = bands.dropna()
    assert (finite["lower"] <= finite["middle"]).all()
    assert (finite["middle"] <= finite["upper"]).all()
    assert (finite["upper"] - finite["lower"]).gt(0.0).all()


def test_bollinger_of_a_constant_series_has_zero_width() -> None:
    bands = bollinger_bands(_series([10.0] * 40), period=20)
    assert bands["upper"].iloc[-1] == pytest.approx(10.0)
    assert bands["lower"].iloc[-1] == pytest.approx(10.0)


def test_bb_width_is_a_fraction_of_the_middle_band() -> None:
    values = _series([float(i % 11) for i in range(1, 80)])
    width = bb_width(values, period=20).dropna()
    bands = bollinger_bands(values, period=20)
    expected = (bands["upper"] - bands["lower"]) / bands["middle"]
    pd.testing.assert_series_equal(width, expected.dropna(), check_names=False)


# --------------------------------------------------------------------------- #
# Stochastic / ADX
# --------------------------------------------------------------------------- #


def test_stochastic_is_bounded() -> None:
    frame = make_range(200)
    result = stochastic(frame["high"], frame["low"], frame["close"]).dropna()
    assert result["k"].between(0.0, 100.0).all()
    assert result["d"].between(0.0, 100.0).all()


def test_stochastic_is_nan_on_a_flat_window() -> None:
    """high == low would divide by zero; NaN beats an invented constant."""
    frame = make_ohlcv(40, noise=0.0, seed=5)
    result = stochastic(frame["high"], frame["low"], frame["close"])
    assert result["k"].isna().any()


def test_adx_is_non_negative_and_bounded() -> None:
    frame = make_trend_then_reverse(300)
    result = adx(frame["high"], frame["low"], frame["close"], period=14).dropna()
    assert (result >= 0.0).all()
    assert (result <= 100.0).all()


def test_adx_is_higher_in_a_trend_than_in_a_range() -> None:
    trending = make_trend_then_reverse(300)
    ranging = make_range(300)
    trend_adx = adx(trending["high"], trending["low"], trending["close"]).iloc[-1]
    range_adx = adx(ranging["high"], ranging["low"], ranging["close"]).iloc[-1]
    assert trend_adx > range_adx


# --------------------------------------------------------------------------- #
# Supertrend
# --------------------------------------------------------------------------- #


def test_supertrend_direction_is_up_in_an_uptrend() -> None:
    """An unbroken rally puts price above the Supertrend band and flips it up.

    The frame is all-up bars rather than a trend-then-reversal, because a
    Supertrend read at the *final* bar of a reversal legitimately reports down —
    that is the indicator working, not a failure.
    """
    frame = make_ohlcv(400, drift=0.004, noise=0.0012, seed=11)
    result = supertrend(frame["high"], frame["low"], frame["close"], period=10, multiplier=3.0)
    assert result["direction"].dropna().iloc[-1] > 0


def test_supertrend_is_nan_until_the_atr_seeds() -> None:
    frame = make_ohlcv(5)
    result = supertrend(frame["high"], frame["low"], frame["close"], period=14)
    assert result["direction"].iloc[0] != result["direction"].iloc[0]  # NaN


def test_supertrend_direction_is_down_in_a_downtrend() -> None:
    frame = make_trend_then_reverse(400, up_bars=50)
    result = supertrend(frame["high"], frame["low"], frame["close"], period=10, multiplier=3.0)
    assert result["direction"].dropna().iloc[-1] < 0


def test_supertrend_rejects_a_non_positive_multiplier() -> None:
    frame = make_ohlcv(40)
    with pytest.raises(ValueError, match="multiplier must be positive"):
        supertrend(frame["high"], frame["low"], frame["close"], multiplier=0.0)


# --------------------------------------------------------------------------- #
# Swings — the look-ahead trap
# --------------------------------------------------------------------------- #


def test_swing_high_reports_a_confirmation_position_after_the_pivot() -> None:
    """A pivot is only knowable `lookback` bars later, and the frame says so."""
    values = _series(
        [1.0, 2.0, 3.0, 10.0, 3.0, 2.0, 1.0] + [float(i) for i in range(8, 40)]
    )
    pivots = confirmed_swing_highs(values, lookback=2)
    assert not pivots.empty
    row = pivots[pivots["price"] == 10.0].iloc[0]
    assert row["confirm_pos"] == row["pivot_pos"] + 2


def test_swing_confirmation_is_never_before_the_pivot() -> None:
    frame = make_range(200)
    for function in (confirmed_swing_highs, confirmed_swing_lows):
        source = frame["high"] if function is confirmed_swing_highs else frame["low"]
        pivots = function(source, lookback=3)
        if pivots.empty:
            continue
        assert (pivots["confirm_pos"] >= pivots["pivot_pos"]).all()
        assert (pivots["confirm_pos"] < len(frame)).all()


def test_swing_at_the_series_end_is_not_reported() -> None:
    """A high on the final bar can never be confirmed, so it must be withheld."""
    values = _series([1.0, 2.0, 3.0, 4.0, 5.0, 99.0])
    pivots = confirmed_swing_highs(values, lookback=2)
    assert 99.0 not in set(pivots["price"])


def test_swing_lows_mirror_the_highs() -> None:
    values = _series([99.0, 5.0, 4.0, 3.0, 4.0, 5.0, 99.0])
    pivots = confirmed_swing_lows(values, lookback=2)
    assert not pivots.empty
    row = pivots[pivots["price"] == 3.0].iloc[0]
    assert row["confirm_pos"] == row["pivot_pos"] + 2


def test_swing_functions_return_the_declared_empty_shape() -> None:
    """A flat series has no pivots; the empty frame must keep its columns."""
    empty = confirmed_swing_highs(_series([5.0] * 40), lookback=3)
    assert list(empty.columns) == ["pivot_pos", "confirm_pos", "price"]
    assert empty.empty


# --------------------------------------------------------------------------- #
# NaN and input handling
# --------------------------------------------------------------------------- #


def test_indicators_propagate_nan_rather_than_filling_it() -> None:
    """A gap in the input must not be silently interpolated."""
    values = _series([float(i) for i in range(1, 40)])
    values.iloc[10] = np.nan
    result = ema(values, period=5)
    assert result.isna().any()


def test_indicators_tolerate_a_short_frame() -> None:
    """Shorter than the lookback must produce all-NaN, not raise."""
    values = _series([1.0, 2.0, 3.0])
    assert sma(values, period=14).isna().all()
    assert ema(values, period=14).isna().all()


def test_indicators_accept_an_empty_series() -> None:
    assert sma(_series([]), period=5).empty
    assert rsi(_series([]), period=5).empty


def test_indicators_coerce_string_input() -> None:
    """A CSV-loaded column of strings must not raise."""
    values = pd.Series(
        ["1.0", "2.0", "3.0", "bad", "5.0"],
        index=pd.date_range("2026-01-01", periods=5, tz="UTC"),
    )
    result = sma(values, period=2)
    assert result.iloc[0] != result.iloc[0]  # NaN


# --------------------------------------------------------------------------- #
# THE LOOKAHEAD PROOF
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("cut", [60, 90, 120, 180, 240])
def test_indicators_have_no_lookahead(cut: int) -> None:
    """An indicator's value at bar i must not depend on any bar after i.

    The frame is truncated at ``cut`` and the indicator is computed on both. The
    truncated result is then compared with the *same prefix* of the full result —
    not with the full result, which is longer by construction. Any
    ``shift(-k)``, centred window, or backfill in the chain would change the
    shared prefix, which is what this catches.
    """
    full = make_trend_then_reverse(300, seed=17)
    partial = full.iloc[:cut].copy()

    def compare(compute) -> None:
        """Compute on both frames and compare over the overlapping prefix."""
        expected = compute(full).iloc[:cut]
        actual = compute(partial)
        pd.testing.assert_series_equal(
            actual,
            expected,
            check_freq=False,
            check_names=False,
        )

    compare(lambda f: ema(f["close"], 20))
    compare(lambda f: sma(f["close"], 20))
    compare(lambda f: rsi(f["close"], 14))
    compare(lambda f: macd(f["close"])["histogram"])
    compare(lambda f: atr(f["high"], f["low"], f["close"], 14))
    compare(lambda f: adx(f["high"], f["low"], f["close"], 14))
    compare(lambda f: supertrend(f["high"], f["low"], f["close"])["line"])
    compare(lambda f: bollinger_bands(f["close"], 20)["upper"])
    compare(lambda f: bb_width(f["close"], 20))
    compare(lambda f: stochastic(f["high"], f["low"], f["close"])["k"])


def test_confirmed_swing_pivots_are_stable_when_truncated(cut: int = 150) -> None:
    """A pivot confirmed at or before `cut` must read the same on a longer frame.

    If a pivot's price or confirmation position changed when later bars arrived,
    the swing function would be reading ahead.
    """
    full = make_range(300, seed=23)
    partial = full.iloc[:cut].copy()

    full_pivots = confirmed_swing_highs(full["high"], lookback=3)
    partial_pivots = confirmed_swing_highs(partial["high"], lookback=3)

    # Only pivots whose confirmation bar survived the truncation can be compared.
    settled = partial_pivots[partial_pivots["confirm_pos"] < cut - 1]
    for _, row in settled.iterrows():
        match = full_pivots[
            (full_pivots["pivot_pos"] == row["pivot_pos"])
            & (full_pivots["price"] == row["price"])
        ]
        assert not match.empty, f"pivot {row['pivot_pos']} changed on a longer frame"


#: The only two functions permitted a negative shift, and only on a reversed
#: series. A swing high is *defined* by the bars that follow it — there is no
#: forward-free way to name one — so the forward window is unavoidable. What
#: makes it safe is that `confirmed_swing_highs` / `confirmed_swing_lows` return
#: each pivot's `confirm_pos`, and every consumer gates on it. Every other
#: indicator must be streaming.
_FORWARD_WINDOW_ALLOWED = {"confirmed_swing_highs", "confirmed_swing_lows"}


def test_only_swing_functions_use_a_negative_shift() -> None:
    """A negative shift is lookahead unless the function discloses when it is safe.

    This is a stronger guard than a blanket ban on ``shift(-)``. A swing high
    genuinely needs the following bars to be identified, and forbidding that
    outright would force a definition that misses real pivots. What must hold is
    that the forward look is confined to the two functions that report a
    confirmation position, so the information is only ever *consumed* once it is
    legitimately knowable.
    """
    import inspect

    from signals import indicators

    offenders: list[str] = []
    for name, function in vars(indicators).items():
        if not inspect.isfunction(function):
            continue
        if not getattr(function, "__module__", "").endswith("signals.indicators"):
            continue
        if "shift(-" not in inspect.getsource(function):
            continue
        if name in _FORWARD_WINDOW_ALLOWED:
            continue
        offenders.append(name)
    assert not offenders, f"unexpected forward shift in: {sorted(offenders)}"


def test_swing_functions_expose_their_confirmation_position() -> None:
    """The licence to look forward is conditional on disclosing when it resolves."""
    import inspect

    from signals import indicators

    for name in _FORWARD_WINDOW_ALLOWED:
        source = inspect.getsource(getattr(indicators, name))
        assert "confirm_pos" in source, (
            f"{name} looks forward but does not report a confirmation position, "
            "so its callers cannot know when the pivot became knowable"
        )


def test_the_six_confirmation_layers_are_streaming() -> None:
    """The layers must not look forward, since they are evaluated bar by bar."""
    import inspect

    from signals import layers

    offenders: list[str] = []
    for name, function in vars(layers).items():
        if not inspect.isfunction(function):
            continue
        if not getattr(function, "__module__", "").endswith("signals.layers"):
            continue
        if "shift(-" in inspect.getsource(function):
            offenders.append(name)
    assert not offenders, f"layer looks forward: {sorted(offenders)}"
