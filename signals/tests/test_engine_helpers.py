"""Shared reference computation for the integration tests.

Both :mod:`test_integration` and :mod:`test_engine` need "the signals this exact
frame produces", and they must agree. Rather than duplicate the engine setup — a
copy that drifts and quietly weakens both suites — the configuration lives here
once.
"""

from __future__ import annotations

import pandas as pd

from signals.engine import SignalEngine
from signals.models import Signal, SignalConfig
from signals.tests.factories import make_trend_then_reverse

#: Frame seed used for the reference signals. Fixed, so the reference is stable.
REFERENCE_SEED = 601
REFERENCE_BARS = 600


def reference_frame() -> pd.DataFrame:
    """The fixture frame the reference signals are computed from."""
    return make_trend_then_reverse(REFERENCE_BARS, seed=REFERENCE_SEED)


def reference_config() -> SignalConfig:
    """The permissive configuration the integration tests use.

    Short lookbacks so a 600-bar fixture clears warmup several times over, and
    no mandatory layers so suppression behaviour is exercised in isolation.
    """
    return SignalConfig(
        mode="aggressive",
        confidence_threshold=0.25,
        mandatory_layers=(),
        min_bars_between_signals=20,
        ema_fast=10,
        ema_slow=30,
        sr_lookback=3,
        volume_ma_period=5,
        bb_period=5,
    )


def compute_reference_signals() -> list[Signal]:
    """The signals the reference frame produces, chronologically."""
    frame = reference_frame()
    engine = SignalEngine(reference_config())
    signals = engine.compute(
        frame, "XAUUSD", "H1", now=frame.index[-1] + pd.Timedelta(days=1)
    )
    assert signals, "reference frame produced no signals"
    return signals
