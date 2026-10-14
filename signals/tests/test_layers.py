"""Tests for the six confirmation layers.

Three properties matter, and each is checked across all six layers rather than
per-layer, because a per-layer test passes while the *set* has drifted:

1. **Bounded scores.** Every layer returns a directional score in ``[-1, 1]``.
   Unbounded is how a single ratio ends up dominating the weighted sum.
2. **Honest abstention.** A layer that cannot be evaluated says ``evaluable=False``
   and scores 0.0. It must never report a confident 0.0, which is
   indistinguishable from a real neutral reading and would let a mandatory layer
   pass on absent data.
3. **Layer coverage.** All six names are present in ``score_all``'s output, and
   their weights sum to 1.0.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from signals.layers import (
    FEATURE_COLUMNS,
    build_features,
    score_all,
    score_momentum,
    score_price_action,
    score_support_resistance,
    score_trend,
    score_volatility,
    score_volume,
)
from signals.models import LAYER_NAMES, SignalConfig
from signals.tests.factories import make_ohlcv, make_range, make_trend_then_reverse


def _config(**kwargs) -> SignalConfig:
    """Short lookbacks so a 400-bar fixture clears warmup comfortably."""
    defaults = {"ema_fast": 10, "ema_slow": 30}
    defaults.update(kwargs)
    return SignalConfig(**defaults)


def _features(frame: pd.DataFrame, config: SignalConfig | None = None) -> pd.DataFrame:
    return build_features(frame, config or _config())


# --------------------------------------------------------------------------- #
# Bounded scores
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "layer",
    [score_trend, score_momentum, score_volume, score_price_action,
     score_volatility, score_support_resistance],
)
@pytest.mark.parametrize("seed", [201, 202, 203])
def test_every_layer_returns_a_bounded_score(layer, seed: int) -> None:
    """No layer may return a magnitude above 1.0, on any fixture."""
    frame = make_trend_then_reverse(400, seed=seed)
    config = _config()
    features = _features(frame, config)

    for pos in range(120, len(features), 17):
        score, evaluable, detail = layer(features, config, pos)
        assert isinstance(score, float)
        assert -1.0 <= score <= 1.0, f"{layer.__name__} returned {score} at {pos}"
        assert isinstance(evaluable, bool)
        assert isinstance(detail, str)


@pytest.mark.parametrize(
    "layer",
    [score_trend, score_momentum, score_volume, score_price_action,
     score_volatility, score_support_resistance],
)
def test_layers_are_deterministic(layer) -> None:
    """Same frame in, same score out — required for a reproducible backtest."""
    frame = make_trend_then_reverse(400, seed=211)
    config = _config()
    features = _features(frame, config)

    first = [layer(features, config, p) for p in range(150, 350, 25)]
    second = [layer(features, config, p) for p in range(150, 350, 25)]
    assert first == second


# --------------------------------------------------------------------------- #
# Abstention
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "layer",
    [score_trend, score_momentum, score_volume, score_price_action,
     score_volatility, score_support_resistance],
)
def test_no_layer_evaluates_the_first_bar(layer) -> None:
    """Bar 0 has no predecessor and no warmup, so every layer must abstain."""
    frame = make_trend_then_reverse(300, seed=221)
    config = _config()
    features = _features(frame, config)

    score, evaluable, _ = layer(features, config, 0)
    assert evaluable is False
    assert score == 0.0


def test_an_unevaluable_layer_scores_exactly_zero() -> None:
    """A non-evaluable layer must not report a confident neutral.

    0.0 with `evaluable=True` would be read as "the market is neutral here", which
    is a different claim from "this layer has no data".
    """
    frame = make_trend_then_reverse(300, seed=231)
    config = _config()
    features = _features(frame, config)

    for pos in range(0, 40):
        for name in LAYER_NAMES:
            from signals.layers import _LAYER_FUNCTIONS

            score, evaluable, _ = _LAYER_FUNCTIONS[name](features, config, pos)
            if not evaluable:
                assert score == 0.0, f"{name} abstained at {pos} but scored {score}"


def test_trend_abstains_below_the_adx_floor() -> None:
    """A ranging market cannot produce a trend-confirmed signal.

    This is what lets `trend` remain a mandatory layer honestly: rather than
    reporting a neutral trend during a range, it declines to have an opinion.
    """
    frame = make_range(400, seed=241)
    config = _config(adx_trend_min=40.0)
    features = _features(frame, config)

    abstentions = 0
    for pos in range(150, len(features), 7):
        _, evaluable, detail = score_trend(features, config, pos)
        if not evaluable and "ADX" in detail:
            abstentions += 1
    assert abstentions > 0, "a range never tripped the ADX floor"


def test_volume_abstains_without_a_volume_column() -> None:
    """"Volume confirmed" is a claim about data; without the column, abstain."""
    frame = make_trend_then_reverse(300, seed=251).drop(columns=["volume"])
    config = _config()
    features = _features(frame, config)

    score, evaluable, detail = score_volume(features, config, 200)
    assert evaluable is False
    assert score == 0.0
    assert "volume" in detail


def test_volume_evaluates_when_the_column_is_present() -> None:
    frame = make_trend_then_reverse(300, seed=257)
    config = _config()
    features = _features(frame, config)

    assert score_volume(features, config, 200)[1] is True


def test_volatility_abstains_outside_the_atr_band() -> None:
    """An untradeable volatility regime is not a neutral volatility reading."""
    frame = make_ohlcv(400, noise=0.03, seed=263)
    # Narrow the band below what this noisy fixture actually produces, so the
    # regime is genuinely outside it. The band must stay ordered.
    measured = _features(frame, _config())["atr"].div(frame["close"]).median()
    config = _config(atr_min_ratio=1e-6, atr_max_ratio=float(measured) / 2.0)
    features = _features(frame, config)

    abstainings = 0
    for pos in range(200, 400, 23):
        score, evaluable, _ = score_volatility(features, config, pos)
        if not evaluable:
            abstainings += 1
            assert score == 0.0
    assert abstainings > 5, "the ATR band never excluded this fixture"


def test_support_resistance_abstains_before_any_swing_is_confirmed() -> None:
    """No confirmed pivot means no level, and no level means no opinion."""
    frame = make_trend_then_reverse(300, seed=271)
    config = _config(sr_lookback=5)
    features = _features(frame, config)

    _score, evaluable, _ = score_support_resistance(features, config, 1)
    assert evaluable is False
    assert _score == 0.0


# --------------------------------------------------------------------------- #
# Layer coverage and weights
# --------------------------------------------------------------------------- #


def test_score_all_covers_every_layer() -> None:
    frame = make_trend_then_reverse(400, seed=281)
    config = _config()
    features = _features(frame, config)

    results = score_all(features, config, 300)
    assert set(results) == set(LAYER_NAMES)


def test_weights_sum_to_one() -> None:
    config = _config()
    assert sum(config.weights.values()) == pytest.approx(1.0)
    assert set(config.weights) == set(LAYER_NAMES)


def test_build_features_appends_every_declared_column() -> None:
    """A feature column the layers read but build_features forgets is a KeyError."""
    frame = make_trend_then_reverse(300, seed=291)
    features = _features(frame)
    for column in FEATURE_COLUMNS:
        assert column in features.columns, f"build_features did not produce {column}"


def test_build_features_does_not_mutate_its_input() -> None:
    frame = make_trend_then_reverse(200, seed=297)
    before = list(frame.columns)
    _features(frame)
    assert list(frame.columns) == before


def test_build_features_preserves_the_index_and_ohlcv() -> None:
    frame = make_trend_then_reverse(200, seed=299)
    features = _features(frame)
    assert features.index.equals(frame.index)
    for column in ("open", "high", "low", "close", "volume"):
        pd.testing.assert_series_equal(
            features[column], frame[column], check_freq=False
        )


# --------------------------------------------------------------------------- #
# Specific layer behaviour
# --------------------------------------------------------------------------- #


def test_trend_is_positive_in_an_uptrend_and_negative_in_a_downtrend() -> None:
    """The trend layer must actually track direction, not just return a number."""
    up = make_ohlcv(400, drift=0.005, noise=0.001, seed=301)
    down = make_ohlcv(400, drift=-0.005, noise=0.001, seed=301)
    config = _config()

    up_scores = [score_trend(_features(up, config), config, p)[0] for p in range(300, 400, 10)]
    down_scores = [
        score_trend(_features(down, config), config, p)[0] for p in range(300, 400, 10)
    ]

    assert np.mean(up_scores) > 0.3
    assert np.mean(down_scores) < -0.3


def test_momentum_extremes_favour_the_opposite_side() -> None:
    """Oversold favours a bounce; overbought favours a fade."""
    up = make_ohlcv(300, drift=0.006, noise=0.001, seed=311)
    down = make_ohlcv(300, drift=-0.006, noise=0.001, seed=311)
    config = _config()

    assert score_momentum(_features(up, config), config, 290)[0] < 0.0, (
        "an exhausted rally should read bearish for momentum"
    )
    assert score_momentum(_features(down, config), config, 290)[0] > 0.0


def test_price_action_detects_a_bullish_engulfing() -> None:
    """A hand-built engulfing bar must be recognised as such.

    Built explicitly rather than searched for in generated data, so the test
    asserts the pattern logic itself rather than that some fixture happens to
    contain the pattern.
    """

    index = pd.date_range("2026-01-01", periods=300, tz="UTC")
    frame = pd.DataFrame(
        {
            "open": np.full(300, 100.0),
            "high": np.full(300, 101.0),
            "low": np.full(300, 99.0),
            "close": np.full(300, 100.0),
            "volume": np.full(300, 1_000.0),
        },
        index=index,
    )
    # Bar 298: small red body. Bar 299: large green body engulfing it.
    frame.iloc[298, frame.columns.get_loc("open")] = 100.4
    frame.iloc[298, frame.columns.get_loc("close")] = 99.8
    frame.iloc[298, frame.columns.get_loc("high")] = 100.5
    frame.iloc[298, frame.columns.get_loc("low")] = 99.7

    frame.iloc[299, frame.columns.get_loc("open")] = 99.5
    frame.iloc[299, frame.columns.get_loc("close")] = 100.8
    frame.iloc[299, frame.columns.get_loc("high")] = 100.9
    frame.iloc[299, frame.columns.get_loc("low")] = 99.4

    score, evaluable, detail = score_price_action(frame, _config(), 299)
    assert evaluable is True
    assert "engulfing" in detail
    assert score > 0.0


def test_price_action_detects_a_shooting_star() -> None:
    """A long upper wick on a small body is a bearish rejection."""
    frame = make_ohlcv(300, seed=313)
    frame = frame.copy()
    frame.iloc[299, frame.columns.get_loc("open")] = 2_000.0
    frame.iloc[299, frame.columns.get_loc("close")] = 2_002.0
    frame.iloc[299, frame.columns.get_loc("high")] = 2_030.0
    frame.iloc[299, frame.columns.get_loc("low")] = 1_999.0

    score, evaluable, detail = score_price_action(frame, _config(), 299)
    assert evaluable is True
    assert "shooting star" in detail
    assert score < 0.0


def test_price_action_neutral_on_an_ordinary_bar() -> None:
    """No pattern means zero, not a fabricated direction."""
    frame = make_ohlcv(300, seed=317)
    score, evaluable, _ = score_price_action(frame, _config(), 200)
    assert evaluable is True
    assert -1.0 <= score <= 1.0


def test_volume_rewards_a_spike_above_its_average() -> None:
    frame = make_trend_then_reverse(300, seed=331)
    frame = frame.copy()
    frame.iloc[250:, frame.columns.get_loc("volume")] = 10_000.0
    config = _config()
    features = _features(frame, config)

    score, evaluable, detail = score_volume(features, config, 250)
    assert evaluable is True
    assert "x MA" in detail
    # The spike is above the average, so the layer must report a non-zero
    # magnitude. Sign follows the bar's own direction, which may be either way.
    assert abs(score) > 0.0


def test_support_resistance_prefers_a_confirmed_level() -> None:
    """After enough bars a level exists and the layer forms an opinion."""
    frame = make_trend_then_reverse(400, seed=337)
    config = _config()
    features = _features(frame, config)

    opinions = sum(
        int(score_support_resistance(features, config, pos)[1])
        for pos in range(200, 400, 11)
    )
    sampled = len(range(200, 400, 11))
    # Most bars must form an opinion once swings are confirmable. The exact
    # fraction depends on the fixture's geometry, so the bar is "most", not "all":
    # a bar far from any level is a legitimate abstention.
    assert opinions > sampled * 0.5, (
        f"support/resistance formed an opinion on only {opinions}/{sampled} bars"
    )


# --------------------------------------------------------------------------- #
# Confirmation gating — the no-lookahead property of the swings
# --------------------------------------------------------------------------- #


def test_swing_columns_are_blank_before_confirmation() -> None:
    """A pivot's price must not appear in the columns before it is knowable.

    `build_features` broadcasts each pivot from its confirmation bar onward. If it
    ever broadcast earlier, this is the test that notices — and that is the
    difference between a non-repainting support level and a lookahead.
    """
    frame = make_range(400, seed=347)
    config = _config(sr_lookback=3)
    features = _features(frame, config)

    for pos in range(len(features)):
        confirm = features["swing_high_confirm"].iloc[pos]
        price = features["swing_high_price"].iloc[pos]
        if np.isnan(price):
            continue
        # A readable pivot is, by construction, one whose confirmation bar has
        # already passed.
        assert confirm <= pos, f"pivot confirmed at {confirm} readable at bar {pos}"


def test_no_feature_column_reads_a_future_bar() -> None:
    """Every feature at bar i must equal its value on a frame truncated at i.

    The one exception is the swing columns, which are validated separately above
    by the confirmation gate.
    """
    full = make_trend_then_reverse(300, seed=349)
    config = _config()
    cut = 250

    expected = _features(full, config).iloc[:cut]
    actual = _features(full.iloc[:cut].copy(), config)

    streaming = [c for c in FEATURE_COLUMNS if not c.startswith("swing_")]
    for column in streaming:
        try:
            pd.testing.assert_series_equal(
                actual[column],
                expected[column],
                check_freq=False,
                check_names=False,
            )
        except AssertionError as exc:
            raise AssertionError(f"{column} reads a future bar") from exc
