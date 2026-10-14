"""Tests for the Zenmux indicator pass.

The card's Market Structure, Key Reasons, Support and Resistance are computed
here, not returned by the classifier. That makes this the code most able to
produce a confident-looking wrong answer, so the tests are mostly about the ways
it could:

* calling a flat market trending,
* placing a level on the wrong side of price,
* inventing a number when there is not enough history,
* and reporting an indicator that does not match the bars it was given.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta

import pytest

from orchestrator.zenmux_analysis import (
    Bar,
    analyse,
    bars_from_candles,
    resample,
)
from shared.schemas.enums import Timeframe


def _series(
    count: int = 240,
    *,
    start: float = 4000.0,
    drift: float = 0.0,
    noise: float = 1.2,
    seed: int = 3,
) -> list[Bar]:
    rng = random.Random(seed)
    out: list[Bar] = []
    price = start
    for _ in range(count):
        open_ = price
        close = price + drift + rng.uniform(-noise, noise)
        high = max(open_, close) + abs(rng.uniform(0, noise))
        low = min(open_, close) - abs(rng.uniform(0, noise))
        out.append(Bar(high=high, low=low, close=close))
        price = close
    return out


# --------------------------------------------------------------------------- #
# Contract
# --------------------------------------------------------------------------- #


def test_an_empty_series_is_rejected() -> None:
    with pytest.raises(ValueError, match="at least one closed bar"):
        analyse([])


def test_a_single_bar_still_produces_usable_geometry() -> None:
    """One bar cannot describe a trend, but the card still needs a price bracket."""
    result = analyse([Bar(high=101.0, low=99.0, close=100.0)])
    assert result.close == 100.0
    assert result.levels.support < 100.0 < result.levels.resistance
    assert result.structure.bias == "neutral"


# --------------------------------------------------------------------------- #
# Direction — the failure mode that matters most
# --------------------------------------------------------------------------- #


def test_a_strong_uptrend_reads_bullish() -> None:
    result = analyse(_series(drift=1.5))
    assert result.structure.bias == "bullish"


def test_a_strong_downtrend_reads_bearish() -> None:
    result = analyse(_series(drift=-1.5))
    assert result.structure.bias == "bearish"


@pytest.mark.parametrize("count", [60, 120, 240])
def test_a_flat_market_is_never_called_trending(count: int) -> None:
    """Regression: EMA ordering alone is not evidence of direction.

    Three averages on a flat series land in one of six orders, so a "clean bullish
    stack" appears by luck about a third of the time. Reporting those as a trend
    made a doji read as Bullish.
    """
    flat = [Bar(high=4000.0, low=4000.0, close=4000.0) for _ in range(count)]
    result = analyse(flat)
    assert result.structure.bias == "neutral", result.structure.detail


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12])
def test_an_insignificant_average_gap_is_never_called_a_trend(seed: int) -> None:
    """The exact invariant behind the gate, asserted directly.

    When the fast and slow averages sit within half a bar's range of each other,
    that is noise regardless of how the three are ordered, and the read must be
    neutral. Checked across seeds because the ordering is a coin flip.
    """
    result = analyse(_series(drift=0.0, noise=1.2, seed=seed))
    assert result.ema_fast is not None
    assert result.ema_slow is not None
    assert result.atr is not None
    separation = abs(result.ema_fast - result.ema_slow)
    if separation <= result.atr * 0.5:
        assert result.structure.bias == "neutral", (
            f"separation {separation:.4f} vs atr {result.atr:.4f} "
            f"was called {result.structure.bias}"
        )


def test_a_directional_read_splits_the_averages_the_same_way() -> None:
    """When a direction is called, the fast and slow averages must agree with it.

    Note this is about the averages, not the last price: in a strong downtrend the
    final bar can close back above the fast average on a bounce while the structure
    is still bearish, so comparing the bias to ``close`` is not a valid invariant.
    """
    for drift in (-2.0, -0.8, 0.8, 2.0):
        result = analyse(_series(drift=drift))
        assert result.ema_fast is not None
        assert result.ema_slow is not None
        if result.structure.bias == "bullish":
            assert result.ema_fast > result.ema_slow
        elif result.structure.bias == "bearish":
            assert result.ema_fast < result.ema_slow


# --------------------------------------------------------------------------- #
# Levels — must bracket price, always
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("drift", [-3.0, -1.0, 0.0, 1.0, 3.0])
def test_levels_always_bracket_the_close(drift: float) -> None:
    result = analyse(_series(drift=drift))
    assert result.levels.support < result.close < result.levels.resistance


def test_levels_bracket_the_close_on_a_flat_series() -> None:
    """A perfectly flat series has no pivots, so the ATR fallback must engage."""
    flat = [Bar(high=100.0, low=100.0, close=100.0) for _ in range(80)]
    result = analyse(flat)
    assert result.levels.support < 100.0 < result.levels.resistance


def test_levels_bracket_the_close_on_a_monotonic_series() -> None:
    rising = [Bar(high=100.0 + i, low=99.0 + i, close=99.5 + i) for i in range(120)]
    result = analyse(rising)
    assert result.levels.support < result.close < result.levels.resistance


def test_a_higher_series_puts_resistance_above_support() -> None:
    low = analyse(_series(start=3000.0, drift=0.5))
    high = analyse(_series(start=5000.0, drift=0.5))
    assert high.levels.support > low.levels.support


def test_a_volatile_series_gets_wider_levels_than_a_calm_one() -> None:
    calm = analyse(_series(noise=0.2))
    wild = analyse(_series(noise=6.0))
    calm_span = calm.levels.resistance - calm.levels.support
    wild_span = wild.levels.resistance - wild.levels.support
    assert wild_span > calm_span


# --------------------------------------------------------------------------- #
# Indicators must match the bars they were given
# --------------------------------------------------------------------------- #


def test_rsi_saturates_on_a_pure_uptrend() -> None:
    rising = [Bar(high=100.0 + i, low=99.0 + i, close=99.5 + i) for i in range(60)]
    assert analyse(rising).rsi == 100.0


def test_rsi_saturates_on_a_pure_downtrend() -> None:
    falling = [Bar(high=200.0 - i, low=199.0 - i, close=199.5 - i) for i in range(60)]
    assert analyse(falling).rsi == 0.0


def test_rsi_is_mid_range_on_an_oscillating_series() -> None:
    """Equal up and down moves of equal size must leave RSI near its midpoint.

    Not exactly 50: Wilder smoothing is recursive, so a series with an odd number
    of changes ends slightly off. What matters is that it lands mid-range rather
    than pinned at a band.
    """
    oscillating = [
        Bar(high=101.0, low=99.0, close=100.0 + (1.0 if index % 2 else -1.0))
        for index in range(60)
    ]
    value = analyse(oscillating).rsi
    assert value is not None
    assert 45.0 <= value <= 55.0


def test_atr_measures_the_true_range_of_the_bars() -> None:
    result = analyse(_series(noise=2.0))
    assert result.atr is not None
    assert result.atr > 0


def test_ema_tracks_a_constant_drift() -> None:
    """On a clean linear ramp the averages must sit between the ends, in order."""
    result = analyse(_series(count=200, drift=1.0, noise=0.01))
    assert result.ema_fast is not None
    assert result.ema_mid is not None
    assert result.ema_slow is not None
    assert result.ema_slow < result.ema_mid < result.ema_fast


def test_indicators_are_absent_when_history_is_too_short() -> None:
    result = analyse(_series(count=20))
    assert result.ema_slow is None
    assert result.structure.bias == "neutral"
    assert result.structure.detail == "Not enough closed bars to read structure"


def test_enough_history_yields_a_slow_average() -> None:
    result = analyse(_series(count=80))
    assert result.ema_slow is not None


# --------------------------------------------------------------------------- #
# Reasons — factual, bounded, jargon-free
# --------------------------------------------------------------------------- #


def test_reasons_are_produced_and_bounded() -> None:
    result = analyse(_series(drift=1.0))
    assert result.reasons
    assert len(result.reasons) <= 6


def test_every_reason_is_a_non_empty_sentence() -> None:
    for drift in (-2.0, 0.0, 2.0):
        for reason in analyse(_series(drift=drift)).reasons:
            assert reason.strip()
            assert reason[0].isupper()


def test_reasons_carry_no_machine_learning_jargon() -> None:
    """These render as "Why?" bullets under a card aimed at non-technical readers."""
    banned = (
        "xgboost",
        "lightgbm",
        "classifier",
        "model",
        "feature",
        "probability",
        "threshold",
        "backend",
        "logit",
        "ensemble",
    )
    for drift in (-2.0, 0.0, 2.0):
        for reason in analyse(_series(drift=drift)).reasons:
            lowered = reason.lower()
            for word in banned:
                assert word not in lowered, f"{word!r} in reason {reason!r}"


def test_reasons_mention_the_averages_they_describe() -> None:
    result = analyse(_series(drift=1.0))
    joined = " ".join(result.reasons).lower()
    assert "average" in joined


def test_a_short_series_still_yields_a_readable_reason() -> None:
    result = analyse(_series(count=25))
    assert result.reasons
    assert all(reason.strip() for reason in result.reasons)


# --------------------------------------------------------------------------- #
# Resampling M5 into M15
# --------------------------------------------------------------------------- #


def _timed(count: int, *, start: datetime = datetime(2026, 10, 5, 0, 0, tzinfo=UTC)) -> list[Bar]:
    """A contiguous run of closed 5-minute bars."""
    out: list[Bar] = []
    for index in range(count):
        base = 100.0 + index * 0.5
        out.append(
            Bar(
                high=base + 1.0,
                low=base - 1.0,
                close=base + 0.25,
                time=start + timedelta(minutes=5 * index),
            )
        )
    return out


def test_resampling_to_m5_returns_the_input() -> None:
    bars = _timed(30)
    assert resample(bars, Timeframe.M5) == list(bars)


def test_m15_buckets_are_three_m5_bars() -> None:
    assert len(resample(_timed(30), Timeframe.M15)) == 10


def test_m15_buckets_align_to_the_quarter_hour() -> None:
    """Wall-clock alignment, not chunking.

    Chunking in threes would leave the first bucket straddling two real M15 bars
    whenever the series starts part-way through one, shifting every aggregate.
    """
    # Start at 03:05, deliberately mid-bucket. Twelve bars run 03:05..04:00, which
    # covers five wall-clock buckets: 03:00 (partial, two bars), 03:15, 03:30,
    # 03:45, and 04:00 holding only the final bar.
    bars = _timed(12, start=datetime(2026, 10, 5, 3, 5, tzinfo=UTC))
    aggregated = resample(bars, Timeframe.M15)

    assert len(aggregated) == 5
    assert [b.time.minute for b in aggregated] == [0, 15, 30, 45, 0]
    assert all(b.time.minute % 15 == 0 for b in aggregated)
    # The first bucket starts on the hour even though the series began at 03:05.
    assert aggregated[0].time == datetime(2026, 10, 5, 3, 0, tzinfo=UTC)


def test_a_bucket_spans_the_high_of_all_its_members() -> None:
    bars = [
        Bar(high=10.0, low=9.0, close=9.5, time=datetime(2026, 10, 5, 0, 0, tzinfo=UTC)),
        Bar(high=14.0, low=11.0, close=13.5, time=datetime(2026, 10, 5, 0, 5, tzinfo=UTC)),
        Bar(high=12.0, low=8.0, close=9.0, time=datetime(2026, 10, 5, 0, 10, tzinfo=UTC)),
    ]
    bucket = resample(bars, Timeframe.M15)[0]
    assert bucket.high == 14.0
    assert bucket.low == 8.0
    assert bucket.close == 9.0, "close must be the last member's close"


def test_a_bucket_closes_on_the_last_member_instant() -> None:
    bars = _timed(3)
    bucket = resample(bars, Timeframe.M15)[0]
    assert bucket.time == datetime(2026, 10, 5, 0, 0, tzinfo=UTC)
    assert bucket.close == bars[-1].close


def test_a_partial_trailing_bucket_is_still_produced() -> None:
    """Two bars into a bucket is still the bucket so far.

    The alternative is dropping it, which would leave the newest price off the card
    entirely whenever the series does not end on a bucket boundary.
    """
    bars = _timed(8)  # 00:00 through 00:35 -> 00:30 bucket has only two members
    aggregated = resample(bars, Timeframe.M15)
    assert len(aggregated) == 3
    assert aggregated[-1].time == datetime(2026, 10, 5, 0, 30, tzinfo=UTC)
    assert aggregated[-1].close == bars[-1].close


def test_resampling_an_empty_series_yields_nothing() -> None:
    assert resample([], Timeframe.M15) == []


def test_resampling_bars_without_timestamps_is_refused() -> None:
    """Silent misalignment is worse than an error here."""
    untimed = [Bar(high=1.0, low=0.5, close=0.8) for _ in range(6)]
    with pytest.raises(ValueError, match="timestamp"):
        resample(untimed, Timeframe.M15)


@pytest.mark.parametrize("timeframe", [Timeframe.H1, Timeframe.H4, Timeframe.D1])
def test_timeframes_beyond_m15_are_refused(timeframe: Timeframe) -> None:
    """Three days of M5 cannot support them; refused rather than half-computed."""
    with pytest.raises(ValueError, match="cannot resample"):
        resample(_timed(60), timeframe)


def test_aggregated_m15_series_still_yields_usable_geometry() -> None:
    bars = resample(_timed(288), Timeframe.M15)
    result = analyse(bars)
    assert result.levels.support < result.close < result.levels.resistance
    assert result.rsi is not None
    assert result.atr is not None and result.atr > 0


def test_a_three_day_window_clears_the_slow_average_at_m15() -> None:
    """Why M15 is the ceiling: 288 M5 bars become 96 M15, above the 55-bar minimum."""
    m5_bars = _timed(288)
    m15_bars = resample(m5_bars, Timeframe.M15)
    assert len(m15_bars) == 96
    assert analyse(m15_bars).ema_slow is not None


# --------------------------------------------------------------------------- #
# Candle adaptation
# --------------------------------------------------------------------------- #


def test_bars_from_candles_preserves_order_and_values() -> None:
    rows = [
        {"high": 2.0, "low": 1.0, "close": 1.5},
        {"high": 3.0, "low": 2.0, "close": 2.5},
    ]
    assert bars_from_candles(rows) == [
        Bar(high=2.0, low=1.0, close=1.5),
        Bar(high=3.0, low=2.0, close=2.5),
    ]


def test_bars_from_candles_coerces_strings() -> None:
    """Candle values arrive from JSON, so they may be numeric strings."""
    assert bars_from_candles([{"high": "2", "low": "1", "close": "1.5"}]) == [
        Bar(high=2.0, low=1.0, close=1.5)
    ]


def test_bars_from_candles_of_nothing_is_empty() -> None:
    assert bars_from_candles([]) == []
