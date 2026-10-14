"""Bar-anchored signal engine for the Pkay TDAI platform.

The module generates BUY/SELL signals from OHLCV data, anchored to the exact
candle that produced them, and never revising them afterwards.

Quick start::

    from signals import SignalConfig, SignalEngine, frame_from_series

    engine = SignalEngine(SignalConfig(mode="balanced"))
    frame = frame_from_series(await client.get_ohlc("XAUUSD", "H1", limit=300))
    signals = engine.compute(frame, "XAUUSD", "H1", now=pd.Timestamp.utcnow())

Guarantees
----------
**No repainting.** A signal is computed only on bars that have closed. The
trailing bar is skipped unless an explicit ``now`` proves it closed, so a live
signal can appear one bar late but never changes afterwards.

**Correct candle.** ``Signal.timestamp`` is a key of the input frame's index and
``Signal.price`` is that bar's ``close``, read together. There is no code path
that can attach a signal to a neighbouring bar.

**Determinism.** No clock read, no randomness, no module state. Same frame and
same config produce the same signals, so a backtest is reproducible.

**No lookahead.** Indicators use only data up to and including the bar being
scored. Swing levels are consumed only from the bar at which they became
confirmable. Nothing in this package calls ``shift`` with a negative argument.
"""

from __future__ import annotations

from signals.engine import SignalEngine, frame_from_series, signal_close_time
from signals.models import (
    CONFIDENCE_THRESHOLDS,
    DEFAULT_WEIGHTS,
    LAYER_NAMES,
    Signal,
    SignalConfig,
    levels_for,
)
from signals.publisher import SIGNAL_CHANNEL, build_message, publish_signal

__all__ = [
    "CONFIDENCE_THRESHOLDS",
    "DEFAULT_WEIGHTS",
    "LAYER_NAMES",
    "SIGNAL_CHANNEL",
    "Signal",
    "SignalConfig",
    "SignalEngine",
    "build_message",
    "frame_from_series",
    "levels_for",
    "publish_signal",
    "signal_close_time",
]
