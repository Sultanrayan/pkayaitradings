"""Tests for regime detection and adaptive decision weights."""

from __future__ import annotations

import pytest

from shared.regime import (
    MarketRegime,
    RegimeWeights,
    adaptive_weights,
    detect_regime,
)


def test_trending_when_adx_high() -> None:
    assert detect_regime(adx=30.0) is MarketRegime.TRENDING


def test_sideways_when_adx_low() -> None:
    assert detect_regime(adx=18.0) is MarketRegime.SIDEWAYS


def test_volatile_when_atr_spikes() -> None:
    assert detect_regime(adx=15.0, atr=12.0, atr_baseline=4.0) is MarketRegime.VOLATILE


def test_volatile_overrides_trend() -> None:
    assert detect_regime(adx=35.0, atr=10.0, atr_baseline=2.0) is MarketRegime.VOLATILE


def test_missing_atr_baseline_falls_back_to_adx() -> None:
    assert detect_regime(adx=30.0, atr=10.0) is MarketRegime.TRENDING


def test_adaptive_weights_per_regime() -> None:
    assert adaptive_weights(MarketRegime.TRENDING) == RegimeWeights(0.60, 0.20, 0.20)
    assert adaptive_weights(MarketRegime.SIDEWAYS) == RegimeWeights(0.40, 0.35, 0.25)
    assert adaptive_weights(MarketRegime.VOLATILE) == RegimeWeights(0.35, 0.30, 0.35)


def test_weights_always_sum_to_one() -> None:
    for regime in MarketRegime:
        weights = adaptive_weights(regime)
        assert weights.technical + weights.news + weights.risk == pytest.approx(1.0)


def test_regime_weights_reject_invalid_sum() -> None:
    with pytest.raises(ValueError, match=r"sum to 1\.0"):
        RegimeWeights(technical=0.5, news=0.5, risk=0.5)
