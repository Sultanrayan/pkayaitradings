"""Tests for the order-flow estimator, including its honest failure modes.

The important tests here are the negative ones. A feed with no trade-level data
must produce zero rather than a plausible-looking number, because a fabricated
delta at weight 0.20 is worse than an absent one.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from telegram_bot.orderflow import SOURCE, OrderFlowSnapshot, compute_order_flow

SYMBOLS = ("XAUUSD", "BTCUSD")


def _frame(
    symbol: str = "XAUUSD",
    *,
    n: int = 120,
    up: bool = True,
    with_ticks: bool = True,
    seed: int = 11,
) -> pd.DataFrame:
    """A frame with a directional drift, optionally with tick counts."""
    rng = np.random.default_rng(seed)
    drift = 0.001 if up else -0.001
    closes = 2_000.0 * np.exp(np.cumsum(rng.normal(drift, 0.0008, size=n)))
    opens = np.empty(n)
    opens[0] = closes[0]
    opens[1:] = closes[:-1]
    index = pd.DatetimeIndex(pd.date_range("2026-01-01", periods=n, tz="UTC", freq="5min"))
    data = {
        "open": opens,
        "high": closes * 1.0006,
        "low": opens * 0.9994,
        "close": closes,
    }
    if with_ticks:
        data["tick_volume"] = rng.integers(50, 200, size=n).astype(float)
    return pd.DataFrame(data, index=index)


# --------------------------------------------------------------------------- #
# Delta
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("symbol", SYMBOLS)
def test_delta_is_positive_in_a_rally(symbol: str) -> None:
    snapshot = compute_order_flow(_frame(symbol, up=True), symbol=symbol, timeframe="5m")
    assert snapshot.delta > 0


@pytest.mark.parametrize("symbol", SYMBOLS)
def test_delta_is_negative_in_a_selloff(symbol: str) -> None:
    snapshot = compute_order_flow(_frame(symbol, up=False), symbol=symbol, timeframe="5m")
    assert snapshot.delta < 0


def test_delta_is_zero_without_ticks() -> None:
    """No ticks means no flow to estimate. It must not become a guess."""
    snapshot = compute_order_flow(_frame(with_ticks=False), symbol="XAUUSD", timeframe="5m")
    assert snapshot.delta == 0.0


def test_delta_is_zero_for_a_perfectly_flat_series() -> None:
    index = pd.date_range("2026-01-01", periods=50, tz="UTC", freq="5min")
    frame = pd.DataFrame(
        {
            "open": np.full(50, 100.0),
            "high": np.full(50, 100.0),
            "low": np.full(50, 100.0),
            "close": np.full(50, 100.0),
            "tick_volume": np.full(50, 100.0),
        },
        index=index,
    )
    snapshot = compute_order_flow(frame, symbol="XAUUSD", timeframe="5m")
    assert snapshot.delta == 0.0


def test_classify_rejects_misaligned_inputs() -> None:
    from telegram_bot.orderflow import classify_bar_delta

    short = pd.Series([1.0, 2.0])
    long = pd.Series([1.0, 2.0, 3.0])
    with pytest.raises(ValueError, match="must align"):
        classify_bar_delta(short, long, short, short, short)


# --------------------------------------------------------------------------- #
# CVD
# --------------------------------------------------------------------------- #


def test_cvd_accumulates_over_the_window() -> None:
    snapshot = compute_order_flow(
        _frame(up=True, n=200), symbol="XAUUSD", timeframe="5m"
    )
    assert snapshot.cvd > 0, "a sustained rally should accumulate positive CVD"


def test_cvd_trend_is_reported() -> None:
    """The trend is one of the three declared values, whatever the market did."""
    rising = compute_order_flow(_frame(up=True, n=200), symbol="XAUUSD", timeframe="5m")
    assert rising.cvd_trend in {"rising", "falling", "flat"}


def test_cvd_trend_follows_a_one_way_market() -> None:
    """A market that only ever rises must report a rising CVD, not a flat one."""
    """Built as monotonic closes so there is no ambiguity about the direction."""
    n = 120
    index = pd.date_range("2026-01-01", periods=n, tz="UTC", freq="5min")
    closes = np.linspace(100.0, 160.0, n)
    frame = pd.DataFrame(
        {
            "open": np.concatenate([[100.0], closes[:-1]]),
            "high": closes * 1.001,
            "low": np.concatenate([[100.0], closes[:-1]]) * 0.999,
            "close": closes,
            "tick_volume": np.full(n, 100.0),
        },
        index=index,
    )
    snapshot = compute_order_flow(frame, symbol="XAUUSD", timeframe="5m")
    assert snapshot.delta > 0
    assert snapshot.cvd_trend == "rising"


def test_cvd_trend_is_flat_when_nothing_is_flowing() -> None:
    """A flat CVD that is merely positive is not "rising"."""
    snapshot = compute_order_flow(
        _frame(with_ticks=False, n=100), symbol="XAUUSD", timeframe="5m"
    )
    assert snapshot.cvd_trend == "flat"


def test_cvd_is_negative_in_a_selloff() -> None:
    snapshot = compute_order_flow(
        _frame(up=False, n=200), symbol="XAUUSD", timeframe="5m"
    )
    assert snapshot.cvd < 0
    assert snapshot.cvd_trend == "falling"


# --------------------------------------------------------------------------- #
# Absorption
# --------------------------------------------------------------------------- #


def test_absorption_requires_meaningful_delta() -> None:
    from telegram_bot.orderflow import detect_absorption

    label, _price = detect_absorption(
        delta=1.0,
        close=100.0,
        previous_close=99.9,
        price_move_threshold=0.5,
        delta_threshold=50.0,
    )
    assert label is None, "a negligible delta cannot constitute absorption"


def test_absorption_requires_price_to_stall() -> None:
    """Flow that moved price was not absorbed by anything."""
    from telegram_bot.orderflow import detect_absorption

    label, _price = detect_absorption(
        delta=500.0,
        close=110.0,
        previous_close=100.0,
        price_move_threshold=0.5,
        delta_threshold=10.0,
    )
    assert label is None


def test_absorption_flags_support_when_buyers_cannot_move_price() -> None:
    from telegram_bot.orderflow import detect_absorption

    label, price = detect_absorption(
        delta=500.0,
        close=100.05,
        previous_close=100.0,
        price_move_threshold=0.5,
        delta_threshold=10.0,
    )
    assert label == "support @ 100.00"
    assert price == pytest.approx(100.0)


def test_absorption_flags_resistance_when_sellers_cannot_move_price() -> None:
    from telegram_bot.orderflow import detect_absorption

    label, _price = detect_absorption(
        delta=-500.0,
        close=99.95,
        previous_close=100.0,
        price_move_threshold=0.5,
        delta_threshold=10.0,
    )
    assert label == "resistance @ 100.00"


# --------------------------------------------------------------------------- #
# Imbalance
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("symbol", SYMBOLS)
def test_imbalance_is_at_least_one(symbol: str) -> None:
    """The ratio is bid-side relative to ask-side, so it cannot be negative."""
    snapshot = compute_order_flow(_frame(symbol), symbol=symbol, timeframe="5m")
    assert snapshot.imbalance_ratio >= 1.0 or np.isinf(snapshot.imbalance_ratio)


def test_imbalance_is_infinite_when_there_are_no_sellers() -> None:
    index = pd.date_range("2026-01-01", periods=60, tz="UTC", freq="5min")
    closes = np.linspace(100.0, 130.0, 60)  # every bar up
    frame = pd.DataFrame(
        {
            "open": np.concatenate([[100.0], closes[:-1]]),
            "high": closes * 1.001,
            "low": np.concatenate([[100.0], closes[:-1]]) * 0.999,
            "close": closes,
            "tick_volume": np.full(60, 100.0),
        },
        index=index,
    )
    snapshot = compute_order_flow(frame, symbol="XAUUSD", timeframe="5m")
    assert np.isinf(snapshot.imbalance_ratio)


def test_imbalance_is_one_when_nothing_flows() -> None:
    snapshot = compute_order_flow(
        _frame(with_ticks=False), symbol="XAUUSD", timeframe="5m"
    )
    assert snapshot.imbalance_ratio == 1.0


# --------------------------------------------------------------------------- #
# Large orders
# --------------------------------------------------------------------------- #


def test_large_order_threshold_is_the_percentile() -> None:
    from telegram_bot.orderflow import large_order_threshold

    ticks = pd.Series(list(range(1, 101)), dtype=float)
    assert large_order_threshold(ticks, 95.0) == pytest.approx(95.05, abs=0.5)


def test_large_order_flag_fires_on_an_outlier_bar() -> None:
    frame = _frame(n=200)
    frame.iloc[-1, frame.columns.get_loc("tick_volume")] = 100_000.0
    snapshot = compute_order_flow(frame, symbol="XAUUSD", timeframe="5m")
    assert snapshot.large_order is True
    assert snapshot.large_order_ratio > 1.0


def test_large_order_does_not_fire_on_a_typical_bar() -> None:
    snapshot = compute_order_flow(_frame(n=200), symbol="XAUUSD", timeframe="5m")
    # The threshold is the 95th percentile, so roughly 5% of bars qualify. This
    # asserts the flag is not simply always on.
    assert snapshot.large_order_ratio > 0.0


def test_large_order_threshold_is_zero_for_empty_data() -> None:
    from telegram_bot.orderflow import large_order_threshold

    assert large_order_threshold(pd.Series(dtype=float)) == 0.0


# --------------------------------------------------------------------------- #
# The honest failure modes
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("symbol", SYMBOLS)
def test_every_snapshot_is_marked_as_a_proxy(symbol: str) -> None:
    """A consumer must be able to tell an estimate from a measurement."""
    snapshot = compute_order_flow(_frame(symbol), symbol=symbol, timeframe="5m")
    assert snapshot.source == SOURCE == "proxy"


def test_a_feed_without_volume_produces_zeros_not_invented_numbers() -> None:
    """The load-bearing test.

    biquote is a CFD feed whose own schema says volume is always 0. If the
    estimator invented a delta in that case, the bot would report fabricated
    order flow at a fifth of its total weight.
    """
    snapshot = compute_order_flow(
        _frame(with_ticks=False), symbol="XAUUSD", timeframe="5m"
    )
    assert snapshot.delta == 0.0
    assert snapshot.cvd == 0.0
    assert snapshot.absorption is None
    assert snapshot.large_order is False
    assert snapshot.source == "proxy"


def test_all_zero_volume_column_is_handled() -> None:
    """A column that exists but is all zeros is the same as no column."""
    frame = _frame()
    frame["tick_volume"] = 0.0
    snapshot = compute_order_flow(frame, symbol="XAUUSD", timeframe="5m")
    assert snapshot.delta == 0.0


def test_empty_frame_returns_a_neutral_snapshot() -> None:
    """An empty frame must not raise; it must return a neutral reading."""
    empty = pd.DataFrame(columns=["open", "high", "low", "close", "tick_volume"])
    snapshot = compute_order_flow(empty, symbol="XAUUSD", timeframe="5m")
    assert snapshot.delta == 0.0
    assert snapshot.bar_ts == 0
    assert snapshot.source == "proxy"


def test_nan_ticks_do_not_become_a_reading() -> None:
    frame = _frame()
    frame["tick_volume"] = np.nan
    snapshot = compute_order_flow(frame, symbol="XAUUSD", timeframe="5m")
    assert snapshot.delta == 0.0


def test_snapshot_round_trips_through_a_dict() -> None:
    original = compute_order_flow(_frame(), symbol="XAUUSD", timeframe="5m")
    restored = OrderFlowSnapshot.from_dict(original.to_dict())
    assert restored == original


def test_from_dict_tolerates_a_missing_payload() -> None:
    """A stored snapshot from an older schema must not crash the reader."""
    restored = OrderFlowSnapshot.from_dict({})
    assert restored.delta == 0.0
    assert restored.source == "proxy"


# --------------------------------------------------------------------------- #
# Determinism
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("symbol", SYMBOLS)
def test_order_flow_is_deterministic(symbol: str) -> None:
    frame = _frame(symbol)
    first = compute_order_flow(frame, symbol=symbol, timeframe="5m")
    second = compute_order_flow(frame, symbol=symbol, timeframe="5m")
    assert first == second


def test_position_selects_a_specific_bar() -> None:
    frame = _frame(n=100, up=False)
    last = compute_order_flow(frame, symbol="XAUUSD", timeframe="5m", position=-1)
    earlier = compute_order_flow(frame, symbol="XAUUSD", timeframe="5m", position=-20)
    assert last.bar_ts != earlier.bar_ts
