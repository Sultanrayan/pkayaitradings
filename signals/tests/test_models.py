"""Tests for the signal engine's configuration and models."""

from __future__ import annotations

import dataclasses

import pandas as pd
import pytest

from signals.models import (
    CONFIDENCE_THRESHOLDS,
    DEFAULT_WEIGHTS,
    LAYER_NAMES,
    Signal,
    SignalConfig,
    levels_for,
)
from signals.tests.factories import make_ohlcv

# --------------------------------------------------------------------------- #
# SignalConfig validation
# --------------------------------------------------------------------------- #


def test_defaults_match_the_specified_profile() -> None:
    config = SignalConfig()
    assert config.mode == "balanced"
    assert config.min_bars_between_signals == 5
    assert config.confirm_on_close is True
    assert config.mandatory_layers == ("trend",)
    assert config.atr_sl_mult == 1.5
    assert config.atr_tp_mult == 2.5
    assert config.atr_tp2_mult == 4.0
    assert config.ema_fast == 50
    assert config.ema_slow == 200
    assert config.rsi_period == 14
    assert config.rsi_oversold == 30.0
    assert config.rsi_overbought == 70.0
    assert config.volume_ma_period == 20
    assert config.volume_mult == 1.2
    assert config.atr_period == 14


def test_default_weights_sum_to_one_and_cover_every_layer() -> None:
    assert set(DEFAULT_WEIGHTS) == set(LAYER_NAMES)
    assert sum(DEFAULT_WEIGHTS.values()) == pytest.approx(1.0)
    assert DEFAULT_WEIGHTS["trend"] == 0.25
    assert DEFAULT_WEIGHTS["momentum"] == 0.25
    assert DEFAULT_WEIGHTS["volume"] == 0.15
    assert DEFAULT_WEIGHTS["price_action"] == 0.15
    assert DEFAULT_WEIGHTS["volatility"] == 0.10
    assert DEFAULT_WEIGHTS["support_resistance"] == 0.10


def test_threshold_follows_the_mode() -> None:
    assert SignalConfig(mode="aggressive").effective_threshold == 0.40
    assert SignalConfig(mode="balanced").effective_threshold == 0.60
    assert SignalConfig(mode="conservative").effective_threshold == 0.75
    assert CONFIDENCE_THRESHOLDS["conservative"] == 0.75


def test_explicit_threshold_overrides_the_mode() -> None:
    config = SignalConfig(mode="conservative", confidence_threshold=0.2)
    assert config.effective_threshold == 0.2


@pytest.mark.parametrize(
    "kwargs",
    [
        {"weights": {"trend": 1.0}},
        {"weights": {**DEFAULT_WEIGHTS, "trend": 0.9}},
        {"weights": {**DEFAULT_WEIGHTS, "nonsense": 0.1}},
        {"mandatory_layers": ("nonsense",)},
        {"mode": "reckless"},
        {"min_bars_between_signals": -1},
        {"ema_fast": 300, "ema_slow": 200},
        {"rsi_oversold": 80.0, "rsi_overbought": 70.0},
        {"atr_sl_mult": 0.0},
        {"atr_tp_mult": 5.0, "atr_tp2_mult": 4.0},
        {"atr_min_ratio": 0.1, "atr_max_ratio": 0.01},
        {"volume_mult": 0.0},
        {"sr_lookback": 1},
    ],
)
def test_invalid_configurations_are_rejected_at_construction(kwargs: dict) -> None:
    """A bad config fails immediately rather than producing wrong signals later."""
    with pytest.raises(ValueError):
        SignalConfig(**kwargs)


def test_warmup_is_bounded_by_the_slowest_indicator() -> None:
    config = SignalConfig()
    assert config.warmup_bars >= config.ema_slow


# --------------------------------------------------------------------------- #
# Signal immutability and serialisation
# --------------------------------------------------------------------------- #


def _sample_signal() -> Signal:
    return Signal(
        timestamp=pd.Timestamp("2026-01-02T03:00:00Z"),
        symbol="XAUUSD",
        timeframe="H1",
        action="BUY",
        price=2_050.5,
        entry=2_050.5,
        sl=2_040.0,
        tp1=2_060.0,
        tp2=2_070.0,
        atr=7.0,
        confidence=0.72,
        reason="BUY at 0.72 confidence",
        layers={"trend": 0.8, "momentum": 0.6},
    )


def test_signal_is_frozen() -> None:
    """A published signal cannot be edited, so a later market view cannot rewrite it."""
    signal = _sample_signal()
    with pytest.raises(dataclasses.FrozenInstanceError):
        signal.price = 1.0  # type: ignore[misc]


def test_signal_symbol_is_upper_cased_on_construction_path() -> None:
    """`from_dict` normalises the symbol, so a lowercase ticker reads back canonical."""
    payload = _sample_signal().to_dict()
    payload["symbol"] = "xauusd"
    assert Signal.from_dict(payload).symbol == "XAUUSD"


def test_roundtrip_preserves_every_field() -> None:
    original = _sample_signal()
    restored = Signal.from_dict(original.to_dict())
    assert restored == original


def test_to_dict_emits_utc_iso_timestamp() -> None:
    payload = _sample_signal().to_dict()
    assert payload["timestamp"] == "2026-01-02T03:00:00+00:00"
    assert payload["layers"] == {"trend": 0.8, "momentum": 0.6}


def test_to_dict_copies_layers_so_the_signal_cannot_be_mutated() -> None:
    payload = _sample_signal().to_dict()
    payload["layers"]["trend"] = -1.0
    assert _sample_signal().layers["trend"] == 0.8


def test_naive_timestamp_is_localised_not_shifted() -> None:
    payload = _sample_signal().to_dict()
    payload["timestamp"] = "2026-01-02T03:00:00"
    assert Signal.from_dict(payload).timestamp == pd.Timestamp("2026-01-02T03:00:00Z")


def test_non_utc_timestamp_is_converted_to_utc() -> None:
    payload = _sample_signal().to_dict()
    payload["timestamp"] = "2026-01-02T05:00:00+02:00"
    assert Signal.from_dict(payload).timestamp == pd.Timestamp("2026-01-02T03:00:00Z")


def test_from_dict_rejects_an_unknown_action() -> None:
    payload = _sample_signal().to_dict()
    payload["action"] = "WAIT"
    with pytest.raises(ValueError, match="unknown action"):
        Signal.from_dict(payload)


def test_with_levels_returns_a_new_instance() -> None:
    original = _sample_signal()
    revised = original.with_levels(sl=2_030.0, tp1=2_065.0, tp2=2_075.0)
    assert original.sl == 2_040.0
    assert revised.sl == 2_030.0
    assert revised.timestamp == original.timestamp


# --------------------------------------------------------------------------- #
# Level geometry
# --------------------------------------------------------------------------- #


def test_buy_levels_sit_below_entry_for_the_stop() -> None:
    sl, tp1, tp2 = levels_for(
        action="BUY", price=100.0, atr=2.0, sl_mult=1.5, tp_mult=2.5, tp2_mult=4.0
    )
    assert sl == pytest.approx(97.0)
    assert tp1 == pytest.approx(105.0)
    assert tp2 == pytest.approx(108.0)
    assert sl < 100.0 < tp1 < tp2


def test_sell_levels_mirror_the_buy_geometry() -> None:
    sl, tp1, tp2 = levels_for(
        action="SELL", price=100.0, atr=2.0, sl_mult=1.5, tp_mult=2.5, tp2_mult=4.0
    )
    assert sl == pytest.approx(103.0)
    assert tp1 == pytest.approx(95.0)
    assert tp2 == pytest.approx(92.0)
    assert tp2 < tp1 < 100.0 < sl


# --------------------------------------------------------------------------- #
# Input contract
# --------------------------------------------------------------------------- #


def test_factory_frames_satisfy_the_engine_input_contract() -> None:
    """The fixtures must themselves obey the contract the engine enforces."""
    frame = make_ohlcv(20)
    assert isinstance(frame.index, pd.DatetimeIndex)
    assert frame.index.tz is not None
    assert str(frame.index.tz) == "UTC"
    assert frame.index.is_monotonic_increasing
    for column in ("open", "high", "low", "close"):
        assert column in frame.columns
