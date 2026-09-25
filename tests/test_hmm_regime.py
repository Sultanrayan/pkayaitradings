"""Tests for the dependency-free Gaussian HMM regime detector."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from shared.hmm_regime import (
    GaussianHMM,
    HMMRegimeDetector,
    build_regime_features,
    observation_values,
)
from shared.regime import MarketRegime


def test_observation_values_drops_non_finite_rows() -> None:
    data = np.array([[1.0, 2.0], [np.nan, 1.0], [3.0, 4.0], [np.inf, 1.0]])
    cleaned = observation_values(data)
    assert cleaned.shape == (2, 2)


def test_gaussian_hmm_recovers_two_state_series() -> None:
    rng = np.random.default_rng(42)
    states = rng.integers(0, 2, size=400)
    observations = np.where(states == 0, 0.5, -0.5) + rng.normal(0.0, 0.15, size=400)
    model = GaussianHMM(n_states=2, n_iter=50, seed=7)
    model.fit(observations)
    path, _ = model.decode(observations)

    # The recovered state labels may be swapped, so compare both assignments.
    direct = float(np.mean(path == states))
    swapped = float(np.mean(path != states))
    assert max(direct, swapped) > 0.7


def test_gaussian_hmm_rejects_too_few_rows() -> None:
    model = GaussianHMM(n_states=2)
    with pytest.raises(ValueError, match="at least 2 rows"):
        model.fit(np.array([[1.0]]))


def test_detector_returns_bounded_detection() -> None:
    rng = np.random.default_rng(3)
    observations = np.column_stack(
        [
            rng.normal(0.001, 0.01, 200),
            np.abs(rng.normal(0.0, 0.01, 200)),
            rng.uniform(0.002, 0.01, 200),
            rng.uniform(0.0, 0.1, 200),
        ]
    )
    detection = HMMRegimeDetector(n_states=3, seed=1).detect(observations)
    assert detection.regime in {MarketRegime.TRENDING, MarketRegime.SIDEWAYS, MarketRegime.VOLATILE}
    assert detection.label in {"BULL_TREND", "BEAR_TREND", "RANGE", "HIGH_VOL"}
    assert 0.0 <= detection.confidence <= 1.0
    assert len(detection.state_means) == 3


def test_detector_rejects_short_input() -> None:
    with pytest.raises(ValueError, match="Not enough observations"):
        HMMRegimeDetector().detect(np.zeros((3, 4)))


def test_build_regime_features_columns_and_alignment() -> None:
    rng = np.random.default_rng(5)
    close = 100.0 + np.cumsum(rng.normal(0.001, 0.5, 120))
    frame = pd.DataFrame(
        {
            "open": close - 0.2,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "tick_volume": np.linspace(100, 200, 120),
        }
    )
    features = build_regime_features(frame)
    assert features.ndim == 2
    assert features.shape[1] == 4
    assert np.isfinite(features).all()
    assert features.shape[0] >= 80


def test_build_regime_features_handles_missing_volume() -> None:
    rng = np.random.default_rng(6)
    close = 100.0 + np.cumsum(rng.normal(0.0, 0.4, 100))
    frame = pd.DataFrame(
        {
            "open": close - 0.2,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
        }
    )
    features = build_regime_features(frame)
    assert features.ndim == 2
    assert np.isfinite(features).all()


def test_build_regime_features_requires_ohlc() -> None:
    with pytest.raises(ValueError, match="missing columns"):
        build_regime_features(pd.DataFrame({"close": [1.0, 2.0]}))
