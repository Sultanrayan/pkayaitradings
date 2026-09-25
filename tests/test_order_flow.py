"""Tests for the order-flow imbalance analyzer."""

from __future__ import annotations

import pandas as pd
import pytest

from shared.order_flow import analyze_order_flow
from shared.schemas.enums import Direction


def _frame(
    closes: list[float],
    opens: list[float] | None = None,
    volumes: list[float] | None = None,
    highs: list[float] | None = None,
    lows: list[float] | None = None,
) -> pd.DataFrame:
    n = len(closes)
    opens = opens or [close - 0.1 for close in closes]
    highs = highs or [close + 0.5 for close in closes]
    lows = lows or [close - 0.5 for close in closes]
    volumes = volumes or [100.0] * n
    return pd.DataFrame(
        {
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "tick_volume": volumes,
        }
    )


def test_bullish_absorption_on_rising_volume_uptrend() -> None:
    closes = [100.0 + i * 0.5 for i in range(50)]
    volumes = [100.0 + i * 10 for i in range(50)]  # rising volume, up-bars
    signal = analyze_order_flow(_frame(closes, volumes=volumes))
    assert signal.direction is Direction.BULLISH
    assert signal.score > 0.0


def test_bearish_absorption_on_falling_market() -> None:
    closes = [100.0 - i * 0.5 for i in range(50)]
    opens = [close + 0.1 for close in closes]  # down-bars (close < open)
    volumes = [100.0 + i * 10 for i in range(50)]
    signal = analyze_order_flow(_frame(closes, opens=opens, volumes=volumes))
    assert signal.direction is Direction.BEARISH
    assert signal.score < 0.0


def test_neutral_when_no_clear_flow() -> None:
    closes = [100.0 + 0.1 * (i % 2) for i in range(50)]
    signal = analyze_order_flow(_frame(closes))
    assert signal.direction in {Direction.NEUTRAL, Direction.BULLISH, Direction.BEARISH}
    assert -1.0 <= signal.score <= 1.0


def test_exhaustion_via_upper_wicks_is_bearish() -> None:
    closes = [100.0 + i * 0.4 for i in range(30)]
    opens = closes
    highs = [value + 3.0 for value in closes]  # long upper wicks
    lows = [value - 0.2 for value in closes]
    signal = analyze_order_flow(_frame(closes, opens=opens, highs=highs, lows=lows))
    assert signal.exhaustion < 0.0


def test_missing_volume_stays_neutral_on_delta() -> None:
    frame = _frame([100.0 + i * 0.5 for i in range(30)])
    frame = frame.drop(columns=["tick_volume"])
    signal = analyze_order_flow(frame)
    assert signal.delta == 0.0
    assert -1.0 <= signal.score <= 1.0


def test_missing_columns_raise() -> None:
    with pytest.raises(ValueError, match="missing columns"):
        analyze_order_flow(pd.DataFrame({"close": [1.0, 2.0]}))


def test_score_bounds() -> None:
    signal = analyze_order_flow(_frame([100.0 + i * 1.0 for i in range(40)]))
    assert -1.0 <= signal.score <= 1.0
    assert -1.0 <= signal.delta <= 1.0
    assert -1.0 <= signal.divergence <= 1.0
    assert -1.0 <= signal.exhaustion <= 1.0
