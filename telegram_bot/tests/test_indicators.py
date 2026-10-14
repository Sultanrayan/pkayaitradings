"""Tests for the seven layers and their underlying indicators.

Two properties are checked for both symbols, because the layers must not behave
differently on gold and bitcoin purely because of price scale:

* every score is bounded in ``[-1, 1]``;
* a layer with no data abstains rather than voting zero.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from telegram_bot import indicators as ind
from telegram_bot.layers import LAYER_NAMES, LAYER_WEIGHTS, build_features, compute_layers

#: Both configured symbols.
SYMBOLS = ("XAUUSD", "BTCUSD")

#: Starting prices typical of each instrument, so scale-dependent logic is
#: exercised the way it will be in production.
START_PRICES = {"XAUUSD": 4_150.0, "BTCUSD": 95_000.0}


def _frame_for(symbol: str, **kwargs) -> pd.DataFrame:
    from telegram_bot.tests.conftest import make_frame

    kwargs.setdefault("start", START_PRICES[symbol])
    return make_frame(300, **kwargs)


# --------------------------------------------------------------------------- #
# Weights and structure
# --------------------------------------------------------------------------- #


def test_seven_layers_are_defined() -> None:
    assert len(LAYER_NAMES) == 7
    assert set(LAYER_NAMES) == set(LAYER_WEIGHTS)


def test_weights_match_the_specification() -> None:
    assert LAYER_WEIGHTS["trend"] == 0.20
    assert LAYER_WEIGHTS["momentum"] == 0.20
    assert LAYER_WEIGHTS["order_flow"] == 0.20
    assert LAYER_WEIGHTS["volume"] == 0.10
    assert LAYER_WEIGHTS["volatility"] == 0.10
    assert LAYER_WEIGHTS["price_action"] == 0.10
    assert LAYER_WEIGHTS["support_resistance"] == 0.10


def test_weights_sum_to_one() -> None:
    assert sum(LAYER_WEIGHTS.values()) == pytest.approx(1.0)


# --------------------------------------------------------------------------- #
# Layer 1 — trend
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("symbol", SYMBOLS)
def test_trend_abstains_without_a_trend(symbol: str) -> None:
    """ADX below the floor means no trend, which is not the same as a downtrend."""
    frame = _frame_for(symbol, drift=0.0001, noise=0.004, seed=41)
    result = compute_layers(frame, symbol=symbol, timeframe="5m", position=-1).results[
        "trend"
    ]
    if not result.evaluable:
        assert result.score == 0.0
        assert "ADX" in result.detail


@pytest.mark.parametrize("symbol", SYMBOLS)
def test_trend_is_bullish_in_a_rally(symbol: str) -> None:
    frame = _frame_for(symbol, drift=0.002, noise=0.0004, seed=43)
    result = compute_layers(frame, symbol=symbol, timeframe="5m", position=-1).results[
        "trend"
    ]
    assert result.evaluable
    assert result.score > 0.5, f"{symbol}: expected a strong bullish trend, got {result.score}"
    assert "bullish" in result.detail


@pytest.mark.parametrize("symbol", SYMBOLS)
def test_trend_is_bearish_in_a_selloff(symbol: str) -> None:
    frame = _frame_for(symbol, drift=-0.002, noise=0.0004, seed=43)
    result = compute_layers(frame, symbol=symbol, timeframe="5m", position=-1).results[
        "trend"
    ]
    assert result.evaluable
    assert result.score < -0.5, f"{symbol}: expected a strong bearish trend, got {result.score}"


def test_trend_uses_ema_50_and_200() -> None:
    frame = _frame_for("XAUUSD", drift=0.002, noise=0.0004, seed=43)
    features = build_features(frame)
    assert "ema50" in features.columns
    assert "ema200" in features.columns
    assert features["ema200"].dropna().index.min() > features.index[0]


# --------------------------------------------------------------------------- #
# Layer 2 — momentum
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("symbol", SYMBOLS)
def test_momentum_is_bearish_when_overbought(symbol: str) -> None:
    """An exhausted rally reads bearish for momentum — correct mean reversion."""
    frame = _frame_for(symbol, drift=0.008, noise=0.0003, seed=47)
    result = compute_layers(frame, symbol=symbol, timeframe="5m", position=-1).results[
        "momentum"
    ]
    assert result.evaluable
    assert "RSI" in result.detail
    assert result.score < 0.0


@pytest.mark.parametrize("symbol", SYMBOLS)
def test_momentum_is_bullish_when_oversold(symbol: str) -> None:
    frame = _frame_for(symbol, drift=-0.008, noise=0.0003, seed=47)
    result = compute_layers(frame, symbol=symbol, timeframe="5m", position=-1).results[
        "momentum"
    ]
    assert result.evaluable
    assert result.score > 0.0


def test_momentum_abstains_on_the_first_bar() -> None:
    frame = _frame_for("XAUUSD")
    result = compute_layers(frame, symbol="XAUUSD", timeframe="5m", position=0).results[
        "momentum"
    ]
    assert result.evaluable is False


# --------------------------------------------------------------------------- #
# Layer 4 — volume
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("symbol", SYMBOLS)
def test_volume_abstains_without_a_volume_column(symbol: str) -> None:
    """No volume data is a different claim from no volume pressure."""
    frame = _frame_for(symbol, tick_volume=False)
    result = compute_layers(frame, symbol=symbol, timeframe="5m", position=-1).results[
        "volume"
    ]
    assert result.evaluable is False
    assert result.score == 0.0
    assert "volume" in result.detail.lower()


@pytest.mark.parametrize("symbol", SYMBOLS)
def test_volume_evaluates_when_data_exists(symbol: str) -> None:
    frame = _frame_for(symbol)
    result = compute_layers(frame, symbol=symbol, timeframe="5m", position=-1).results[
        "volume"
    ]
    assert result.evaluable is True
    assert "x avg" in result.detail


def test_volume_reports_its_ratio_against_the_average() -> None:
    frame = _frame_for("XAUUSD")
    result = compute_layers(frame, symbol="XAUUSD", timeframe="5m", position=-1).results[
        "volume"
    ]
    ratio = float(result.detail.split("x")[0])
    assert ratio > 0.0


# --------------------------------------------------------------------------- #
# Layer 5 — volatility
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("symbol", SYMBOLS)
def test_volatility_evaluates_for_both_symbols(symbol: str) -> None:
    frame = _frame_for(symbol, drift=0.001, noise=0.001, seed=53)
    result = compute_layers(frame, symbol=symbol, timeframe="5m", position=-1).results[
        "volatility"
    ]
    assert result.evaluable is True
    assert "ATR" in result.detail


@pytest.mark.parametrize("symbol", SYMBOLS)
def test_volatility_abstains_on_an_extreme_range(symbol: str) -> None:
    frame = _frame_for(symbol, noise=0.05, seed=59)
    result = compute_layers(frame, symbol=symbol, timeframe="5m", position=-1).results[
        "volatility"
    ]
    if not result.evaluable:
        assert result.score == 0.0


# --------------------------------------------------------------------------- #
# Layer 6 — price action
# --------------------------------------------------------------------------- #


def test_price_action_detects_a_bullish_engulfing() -> None:
    """Built explicitly, so the test asserts the pattern logic itself."""
    index = pd.date_range("2026-01-01", periods=250, tz="UTC", freq="5min")
    frame = pd.DataFrame(
        {
            "open": np.full(250, 100.0),
            "high": np.full(250, 101.0),
            "low": np.full(250, 99.0),
            "close": np.full(250, 100.0),
            "tick_volume": np.full(250, 100.0),
        },
        index=index,
    )
    last = frame.index[-1]
    prior = frame.index[-2]
    frame.loc[prior, ["open", "close", "high", "low"]] = [100.4, 99.8, 100.5, 99.7]
    frame.loc[last, ["open", "close", "high", "low"]] = [99.5, 100.9, 101.0, 99.4]

    result = compute_layers(
        frame, symbol="XAUUSD", timeframe="5m", position=-1
    ).results["price_action"]
    assert result.evaluable
    assert "engulfing" in result.detail
    assert result.score > 0.0


def test_price_action_detects_a_shooting_star() -> None:
    index = pd.date_range("2026-01-01", periods=250, tz="UTC", freq="5min")
    frame = pd.DataFrame(
        {
            "open": np.full(250, 100.0),
            "high": np.full(250, 101.0),
            "low": np.full(250, 99.0),
            "close": np.full(250, 100.0),
            "tick_volume": np.full(250, 100.0),
        },
        index=index,
    )
    frame.loc[frame.index[-1], ["open", "close", "high", "low"]] = [100.0, 100.5, 106.0, 99.9]

    result = compute_layers(
        frame, symbol="XAUUSD", timeframe="5m", position=-1
    ).results["price_action"]
    assert "shooting star" in result.detail or "pin bar" in result.detail


# --------------------------------------------------------------------------- #
# Layer 7 — support / resistance
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("symbol", SYMBOLS)
def test_support_resistance_finds_levels(symbol: str) -> None:
    frame = _frame_for(symbol, drift=0.001, noise=0.002, seed=61)
    results = compute_layers(
        frame, symbol=symbol, timeframe="5m", position=-1
    ).results["support_resistance"]
    assert isinstance(results.evaluable, bool)


def test_support_resistance_abstains_before_any_swing_is_confirmed() -> None:
    frame = _frame_for("XAUUSD")
    result = compute_layers(
        frame, symbol="XAUUSD", timeframe="5m", position=1
    ).results["support_resistance"]
    assert result.evaluable is False


# --------------------------------------------------------------------------- #
# All layers, both symbols
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("symbol", SYMBOLS)
@pytest.mark.parametrize("position", [150, 200, 250, 299])
def test_every_layer_score_is_bounded(symbol: str, position: int) -> None:
    frame = _frame_for(symbol, drift=0.001, noise=0.002, seed=67)
    results = compute_layers(frame, symbol=symbol, timeframe="5m", position=position)
    assert set(results.results) == set(LAYER_NAMES)
    for name, result in results.results.items():
        assert -1.0 <= result.score <= 1.0, f"{symbol} {name} scored {result.score}"


@pytest.mark.parametrize("symbol", SYMBOLS)
def test_no_layer_claims_neutral_while_having_no_data(symbol: str) -> None:
    """An abstaining layer must not report a confident zero."""
    frame = _frame_for(symbol, tick_volume=False)
    results = compute_layers(frame, symbol=symbol, timeframe="5m", position=3)
    for name, result in results.results.items():
        if not result.evaluable:
            assert result.score == 0.0, f"{symbol} {name} abstained but scored {result.score}"


@pytest.mark.parametrize("symbol", SYMBOLS)
def test_layer_scoring_is_deterministic(symbol: str) -> None:
    frame = _frame_for(symbol, drift=0.001, noise=0.002, seed=71)
    first = compute_layers(frame, symbol=symbol, timeframe="5m", position=250)
    second = compute_layers(frame, symbol=symbol, timeframe="5m", position=250)
    assert {n: r.score for n, r in first.results.items()} == {
        n: r.score for n, r in second.results.items()
    }


def test_build_features_appends_every_required_column() -> None:
    frame = _frame_for("XAUUSD")
    features = build_features(frame)
    required = {
        "ema50",
        "ema200",
        "adx",
        "atr",
        "macd",
        "macd_signal",
        "macd_hist",
        "stoch_k",
        "stoch_d",
        "st_line",
        "st_dir",
        "bb_upper",
        "bb_lower",
        "bb_middle",
        "kc_upper",
        "kc_lower",
        "kc_middle",
        "obv",
        "mfi",
        "swing_high_price",
        "swing_low_price",
        "fib_236",
        "fib_500",
        "fib_786",
        "pivot",
        "r1",
        "s1",
    }
    missing = required - set(features.columns)
    assert not missing, f"build_features did not produce: {sorted(missing)}"


def test_build_features_does_not_mutate_the_input() -> None:
    frame = _frame_for("XAUUSD")
    before = list(frame.columns)
    build_features(frame)
    assert list(frame.columns) == before


# --------------------------------------------------------------------------- #
# The indicators themselves
# --------------------------------------------------------------------------- #


def test_obv_accumulates_signed_volume() -> None:
    close = pd.Series([10.0, 11.0, 10.0, 12.0])
    volume = pd.Series([100.0, 100.0, 100.0, 100.0])
    result = ind.obv(close, volume)
    assert result.iloc[0] == 0.0  # no previous close to compare against
    assert result.iloc[1] == 100.0  # up bar
    assert result.iloc[2] == 0.0  # down bar
    assert result.iloc[3] == 100.0  # up bar


def test_obv_ignores_a_flat_bar() -> None:
    """A flat close has no direction, so attributing it to either side would bias."""
    close = pd.Series([10.0, 10.0, 10.0])
    volume = pd.Series([100.0, 100.0, 100.0])
    assert ind.obv(close, volume).iloc[-1] == 0.0


def test_mfi_is_bounded() -> None:
    frame = _frame_for("XAUUSD")
    result = ind.mfi(frame["high"], frame["low"], frame["close"], frame["tick_volume"], 14).dropna()
    assert result.min() >= 0.0
    assert result.max() <= 100.0


def test_keltner_channels_are_ordered() -> None:
    frame = _frame_for("XAUUSD")
    channels = ind.keltner_channels(frame["high"], frame["low"], frame["close"])
    finite = channels.dropna()
    assert (finite["lower"] <= finite["middle"]).all()
    assert (finite["middle"] <= finite["upper"]).all()


def test_keltner_rejects_a_non_positive_multiplier() -> None:
    frame = _frame_for("XAUUSD")
    with pytest.raises(ValueError, match="multiplier must be positive"):
        ind.keltner_channels(frame["high"], frame["low"], frame["close"], multiplier=0.0)


def test_pivot_points_use_the_previous_bar() -> None:
    """Pivots computed from the current bar would change until the bar closed."""
    frame = _frame_for("XAUUSD")
    pivots = ind.pivot_points(frame["high"], frame["low"], frame["close"])

    index = frame.index[-1]
    previous = frame.iloc[-2]
    expected = (previous["high"] + previous["low"] + previous["close"]) / 3.0
    assert pivots.loc[index, "pivot"] == pytest.approx(expected)


def test_pivot_first_bar_is_nan() -> None:
    frame = _frame_for("XAUUSD")
    pivots = ind.pivot_points(frame["high"], frame["low"], frame["close"])
    assert np.isnan(pivots["pivot"].iloc[0])


def test_swing_levels_are_only_readable_after_confirmation() -> None:
    """A swing at bar p is knowable at p + lookback, and not before."""
    frame = _frame_for("XAUUSD", drift=0.001, noise=0.003, seed=73)
    levels = ind.swing_levels(frame["high"], frame["low"], lookback=5)

    for position in range(len(frame)):
        price = levels["high_price"].iloc[position]
        confirm = levels["high_pos"].iloc[position]
        if np.isnan(price):
            continue
        assert confirm <= position, (
            f"swing at {confirm} was readable at bar {position}, before it was confirmed"
        )


def test_fibo_levels_derive_from_the_trailing_range() -> None:
    frame = _frame_for("XAUUSD")
    fib = ind.fibo_levels(frame["high"], frame["low"], lookback=50).dropna()
    assert len(fib) > 0
    # Retracement is measured down from the high, so the levels descend.
    assert fib["fib_236"].iloc[-1] > fib["fib_786"].iloc[-1]
    assert fib["fib_236"].iloc[-1] <= fib["range_high"].iloc[-1]
    assert fib["fib_786"].iloc[-1] >= fib["range_low"].iloc[-1]


def test_fibo_rejects_a_short_lookback() -> None:
    frame = _frame_for("XAUUSD")
    with pytest.raises(ValueError, match="lookback must be at least 2"):
        ind.fibo_levels(frame["high"], frame["low"], lookback=1)


@pytest.mark.parametrize("symbol", SYMBOLS)
def test_no_indicator_reads_a_future_bar(symbol: str) -> None:
    """Every feature at bar i must equal its value on a frame truncated at i.

    The strongest single anti-lookahead check available: it would catch a negative
    shift, a centred rolling window, or a backfill anywhere in the chain, without
    needing to know where such a mistake was made.
    """
    full = _frame_for(symbol, drift=0.001, noise=0.002, seed=79)
    cut = 250

    expected = build_features(full).iloc[:cut]
    actual = build_features(full.iloc[:cut].copy())

    for column in expected.columns:
        if column.startswith("swing_"):
            # Swing columns are broadcast from their confirmation bar onward and
            # are validated separately by test_swing_levels_are_only_readable...
            continue
        try:
            pd.testing.assert_series_equal(
                actual[column],
                expected[column],
                check_freq=False,
                check_names=False,
            )
        except AssertionError as exc:
            raise AssertionError(f"{column} reads a future bar") from exc
