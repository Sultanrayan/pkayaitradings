"""Tests for the rule-based technical strategy engine."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from agents.technical_analyst.strategy import (
    TechnicalParams,
    compute_indicators,
    evaluate,
    signal_from_composite,
    to_frame,
)
from shared.schemas.enums import Direction
from shared.schemas.market import OhlcBar, OhlcSeries


def make_series(n: int = 300, drift: float = 0.5, seed: int = 7) -> OhlcSeries:
    rng = np.random.default_rng(seed)
    close = 100.0 + np.cumsum(rng.normal(drift, 0.4, n))
    start = datetime(2026, 1, 1, tzinfo=UTC)
    bars = tuple(
        OhlcBar(
            openTime=start + timedelta(hours=i),
            open=float(close[i] - 0.2),
            high=float(close[i] + 0.5),
            low=float(close[i] - 0.5),
            close=float(close[i]),
            volume=0,
            tickVolume=100 + i,
            isOpen=False,
        )
        for i in range(n)
    )
    return OhlcSeries(symbol="XAUUSD", interval="1h", bars=bars)


def test_to_frame_is_chronological() -> None:
    frame = to_frame(make_series(10))
    assert frame.index.is_monotonic_increasing
    assert list(frame.columns) == ["open", "high", "low", "close", "tick_volume", "is_open"]


def test_evaluate_requires_enough_bars() -> None:
    with pytest.raises(ValueError, match="at least"):
        evaluate(to_frame(make_series(10)))


def test_evaluate_uptrend_is_bullish() -> None:
    result = evaluate(to_frame(make_series(300, drift=0.6)))
    assert result.signal is Direction.BULLISH
    assert result.confidence > 0.1
    assert result.key_levels.support is not None
    assert result.key_levels.resistance is not None


def test_evaluate_downtrend_is_bearish() -> None:
    result = evaluate(to_frame(make_series(300, drift=-0.6)))
    assert result.signal is Direction.BEARISH


def test_compute_indicators_adds_expected_columns() -> None:
    enriched = compute_indicators(to_frame(make_series(300)), TechnicalParams())
    for column in ("rsi", "macd_hist", "ema_fast", "ema_slow", "atr", "adx", "bb_upper"):
        assert column in enriched.columns


def test_signal_from_composite_thresholds() -> None:
    """Always directional: no composite value produces NEUTRAL any more."""
    params = TechnicalParams()
    weak, weak_conf = signal_from_composite(0.05, 1.0, params)
    bullish, _ = signal_from_composite(0.5, 1.0, params)
    bearish, _ = signal_from_composite(-0.5, 1.0, params)

    assert weak is Direction.BULLISH, "a small positive lean is still BUY, at low confidence"
    assert weak_conf < 0.30, "the weakness must show up as confidence, not as a refusal"
    assert bullish is Direction.BULLISH
    assert bearish is Direction.BEARISH


@pytest.mark.parametrize(
    "composite",
    [0.0, 0.001, 0.05, 0.14, 0.15, 0.16, -0.001, -0.05, -0.14, -0.15, -0.5, 0.5, 1.0, -1.0],
)
def test_signal_from_composite_never_returns_neutral(composite: float) -> None:
    """The whole point of the change, swept across the full composite range.

    ``neutral_threshold`` used to carve out a band around zero. Every value in
    and around that band must now produce a direction.
    """
    for trend_strength in (0.4, 0.7, 1.0):
        direction, confidence = signal_from_composite(
            composite, trend_strength, TechnicalParams()
        )
        assert direction in {Direction.BULLISH, Direction.BEARISH}
        assert 0.0 <= confidence <= 1.0


def test_a_zero_composite_still_yields_a_direction() -> None:
    """The function must be total. With no edge either way the tie-break is
    arbitrary, but it must be stable rather than raising or returning None."""
    direction, confidence = signal_from_composite(0.0, 1.0, TechnicalParams())
    assert direction in {Direction.BULLISH, Direction.BEARISH}
    assert confidence == pytest.approx(0.05), "confidence is floored, never zero"


def test_confidence_is_floored_above_zero() -> None:
    """Zero confidence alongside a direction reads as a bug to any consumer."""
    _, confidence = signal_from_composite(0.0, 0.4, TechnicalParams())
    assert confidence >= 0.05


def test_compute_indicators_missing_columns_raises() -> None:
    import pandas as pd

    with pytest.raises(ValueError, match="missing columns"):
        compute_indicators(pd.DataFrame({"close": [1.0, 2.0]}), TechnicalParams())
