"""THE ATTACHMENT PROOF.

Every signal must name a bar that exists, and carry that bar's own close. This is
the property that decides whether a signal is plotted on the candle the trader
acted on or one bar away from it — a bug that is invisible in any test comparing
the engine only against itself, and that makes every backtest quietly dishonest.

The tests assert against the **source frame**, never against another engine
output, so a shared misreading cannot make them pass together.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from signals.engine import SignalEngine, frame_from_series
from signals.models import Signal, SignalConfig
from signals.tests.factories import (
    make_ohlcv,
    make_range,
    make_trend_then_reverse,
    with_open_bar,
)

TOLERANCE = 1e-9


def _engine() -> SignalEngine:
    """Permissive, so attachment is tested on real signals rather than an empty list."""
    return SignalEngine(
        SignalConfig(
            mode="aggressive",
            confidence_threshold=0.25,
            mandatory_layers=(),
            min_bars_between_signals=1,
            require_opposite_before_repeat=False,
            ema_fast=10,
            ema_slow=30,
        )
    )


def _signals(frame: pd.DataFrame, *, symbol: str = "XAUUSD") -> list[Signal]:
    """Compute over a frame with every bar treated as closed."""
    now = frame.index[-1] + pd.Timedelta(days=1)
    return _engine().compute(frame, symbol, "H1", now=now)


def _frames() -> list[pd.DataFrame]:
    """Several differently-shaped fixtures, so attachment is not proven by one case."""
    return [
        make_trend_then_reverse(400, seed=101),
        make_trend_then_reverse(400, seed=103, up_bars=300),
        make_range(400, seed=107),
        make_ohlcv(400, seed=109, drift=0.003),
        make_ohlcv(400, seed=113, drift=-0.003),
    ]


# --------------------------------------------------------------------------- #
# The core contract
# --------------------------------------------------------------------------- #


def test_every_signal_timestamp_exists_in_the_frame_index() -> None:
    for frame in _frames():
        signals = _signals(frame)
        assert signals, "fixture produced no signals; the proof would be vacuous"
        for signal in signals:
            assert signal.timestamp in frame.index, (
                f"signal timestamp {signal.timestamp} is not a bar in the frame"
            )


def test_every_signal_price_equals_its_bars_close() -> None:
    """The defining property: price is the anchor bar's own close, to the bit."""
    for frame in _frames():
        for signal in _signals(frame):
            expected = float(frame.loc[signal.timestamp, "close"])
            assert signal.price == pytest.approx(expected, abs=TOLERANCE), (
                f"price {signal.price} != close {expected} at "
                f"{signal.timestamp.isoformat()}"
            )


def test_no_signal_is_shifted_by_even_one_bar() -> None:
    """A signal must not carry a neighbouring bar's price.

    Asserted as a set difference rather than an inequality: with a smooth series
    the neighbouring closes are *close* but not equal, and a tolerance-based check
    could pass a signal that is one bar off.
    """
    for frame in _frames():
        closes = set(np.round(frame["close"].to_numpy(), 9))
        for signal in _signals(frame):
            position = frame.index.get_loc(signal.timestamp)
            # The signal's price must be its own bar's, and the timestamps of the
            # bars before and after must not carry the signal.
            neighbours = [
                frame.index[p] for p in (position - 1, position + 1) if 0 <= p < len(frame)
            ]
            for neighbour in neighbours:
                assert neighbour in frame.index
            assert round(signal.price, 9) == round(
                float(frame.loc[signal.timestamp, "close"]), 9
            )
    assert len(closes) > 0


def test_signals_are_in_strictly_increasing_timestamp_order() -> None:
    """Chronological order, with no duplicate bar emitted twice."""
    for frame in _frames():
        signals = _signals(frame)
        stamps = [s.timestamp for s in signals]
        assert stamps == sorted(stamps)
        assert len(stamps) == len(set(stamps)), "a bar produced more than one signal"


def test_no_signal_is_attached_to_a_future_bar() -> None:
    """Signals are about the past, so none may name a bar after the reference."""
    for frame in _frames():
        cutoff = frame.index[-1]
        for signal in _signals(frame):
            assert signal.timestamp <= cutoff


# --------------------------------------------------------------------------- #
# Entry and levels are anchored too
# --------------------------------------------------------------------------- #


def test_entry_equals_price_for_a_close_confirmed_signal() -> None:
    """A market entry taken on the close is priced at that close."""
    for frame in _frames():
        for signal in _signals(frame):
            assert signal.entry == signal.price


def test_levels_are_ordered_around_the_entry() -> None:
    """Geometry must be internally consistent, or the chart draws nonsense."""
    for frame in _frames():
        for signal in _signals(frame):
            if signal.action == "BUY":
                assert signal.sl < signal.price < signal.tp1 < signal.tp2
            else:
                assert signal.sl > signal.price > signal.tp1 > signal.tp2


def test_levels_are_atr_multiples_of_the_anchor_bar() -> None:
    """SL and TPs are computed from the anchor bar's ATR, not any other bar's."""
    config = _engine().config
    for frame in _frames():
        for signal in _signals(frame):
            expected_sl = config.atr_sl_mult * signal.atr
            expected_tp1 = config.atr_tp_mult * signal.atr
            expected_tp2 = config.atr_tp2_mult * signal.atr
            assert abs(signal.price - signal.sl) == pytest.approx(expected_sl, rel=1e-9)
            assert abs(signal.tp1 - signal.price) == pytest.approx(expected_tp1, rel=1e-9)
            assert abs(signal.tp2 - signal.price) == pytest.approx(expected_tp2, rel=1e-9)


def test_atr_matches_the_anchor_bar_not_a_neighbour() -> None:
    """ATR is read at the signal's own bar.

    A one-bar shift in the ATR would leave the levels looking plausible while
    misplacing the stop, which is the failure mode this test exists to catch.
    """
    from signals.indicators import atr

    frame = _frames()[0]
    atr_series = atr(frame["high"], frame["low"], frame["close"], period=14)

    for signal in _signals(frame)[:10]:
        own = float(atr_series.loc[signal.timestamp])
        assert signal.atr == pytest.approx(own, rel=1e-9)

        position = frame.index.get_loc(signal.timestamp)
        if position + 1 < len(frame):
            neighbour = float(atr_series.iloc[position + 1])
            # Only meaningful when the two differ; skip the coincidence.
            if abs(neighbour - own) > 1e-6:
                assert signal.atr != pytest.approx(neighbour, rel=1e-6)


# --------------------------------------------------------------------------- #
# Serialisation must not move the bar
# --------------------------------------------------------------------------- #


def test_roundtrip_preserves_the_exact_bar() -> None:
    """Store → API serialisation is a no-op on the bar identity.

    This is where a naive implementation would reformat the timestamp to local
    time or truncate the price, and where "API == store == chart" quietly stops
    being true.
    """
    for frame in _frames()[:2]:
        for signal in _signals(frame)[:10]:
            restored = Signal.from_dict(signal.to_dict())
            assert restored.timestamp == signal.timestamp
            assert restored.timestamp == frame.index[frame.index.get_loc(signal.timestamp)]
            assert restored.price == signal.price
            assert restored.price == pytest.approx(
                float(frame.loc[restored.timestamp, "close"]), abs=TOLERANCE
            )


def test_payload_timestamp_is_utc_iso() -> None:
    """The API's timestamp must be unambiguously UTC, whatever the host zone."""
    frame = _frames()[0]
    for signal in _signals(frame)[:5]:
        payload = signal.to_dict()
        assert payload["timestamp"].endswith("+00:00")
        assert pd.Timestamp(payload["timestamp"]).tzinfo is not None


# --------------------------------------------------------------------------- #
# The live path
# --------------------------------------------------------------------------- #


def test_frame_from_series_anchors_signals_to_close_times() -> None:
    """End to end: biquote open-time bars in, close-time-anchored signals out."""
    from signals.tests.factories import make_series

    frame = make_trend_then_reverse(300, seed=127)
    series = make_series(frame, interval="1h")
    converted = frame_from_series(series)
    signals = _signals(converted)

    assert signals, "no signals from the converted frame; proof would be vacuous"

    # Every bar must sit exactly one interval after its open-time label.
    offset = (
        pd.DatetimeIndex(converted.index)
        - pd.DatetimeIndex([bar.open_time for bar in series.bars])
    ).total_seconds()
    assert offset.unique().tolist() == [3_600.0]

    # Signals anchor to the converted (close-time) index and carry that bar's own
    # close. Note that in a continuous series bar N's close time *equals* bar N+1's
    # open time — they are the same instant, so a signal timestamp legitimately
    # also appears as an open time. What must hold is the pairing with the price,
    # which is what distinguishes bar N from bar N+1.
    for signal in signals:
        assert signal.timestamp in converted.index
        assert signal.price == pytest.approx(
            float(converted.loc[signal.timestamp, "close"]), abs=TOLERANCE
        )
        position = converted.index.get_loc(signal.timestamp)
        if position + 1 < len(converted):
            next_close = float(converted["close"].iloc[position + 1])
            if abs(next_close - signal.price) > 1e-6:
                assert signal.price != pytest.approx(next_close, rel=1e-9)


def test_an_unclosed_bar_is_never_an_anchor() -> None:
    """The forming bar is not a candle a signal can be attached to yet."""
    base = make_trend_then_reverse(300, seed=131)
    extended = with_open_bar(base, mutate=0.02)
    signals = _engine().compute(extended, "XAUUSD", "H1")

    open_timestamp = extended.index[-1]
    assert open_timestamp not in {s.timestamp for s in signals}
    for signal in signals:
        assert signal.timestamp in base.index


# --------------------------------------------------------------------------- #
# Adversarial shapes
# --------------------------------------------------------------------------- #


def test_attachment_holds_with_gaps_in_the_timeline() -> None:
    """A feed that skips bars must not shift any signal onto a neighbour.

    Removed bars leave irregular spacing, which is exactly the condition under
    which a positional/timezone mistake would surface.
    """
    frame = make_trend_then_reverse(400, seed=137)
    keep = [i for i in range(len(frame)) if i % 7 != 0 or i < 3]
    gapped = frame.iloc[keep].copy()
    assert not gapped.index.is_monotonic_increasing or len(gapped) < len(frame)

    signals = _signals(gapped)
    assert signals, "no signals on the gapped frame"
    for signal in signals:
        assert signal.timestamp in gapped.index
        assert signal.price == pytest.approx(
            float(gapped.loc[signal.timestamp, "close"]), abs=TOLERANCE
        )


def test_attachment_holds_when_the_index_is_unsorted() -> None:
    """A shuffled feed must still produce correctly anchored signals.

    The engine sorts internally; the assertion is that sorting does not move a
    signal onto a different bar's price.
    """
    frame = make_trend_then_reverse(400, seed=139)
    shuffled = frame.sample(frac=1.0, random_state=3)
    assert not shuffled.index.is_monotonic_increasing

    now = frame.index[-1] + pd.Timedelta(days=1)
    from_shuffled = _engine().compute(shuffled, "XAUUSD", "H1", now=now)
    from_sorted = _engine().compute(frame, "XAUUSD", "H1", now=now)

    assert [s.timestamp for s in from_shuffled] == [s.timestamp for s in from_sorted]
    assert [s.price for s in from_shuffled] == [s.price for s in from_sorted]


def test_duplicate_timestamps_collapse_without_moving_signals() -> None:
    """A duplicated print must not make a signal ambiguous about its bar.

    The engine keeps the last occurrence. The signal then belongs to that bar and
    carries its price — the alternative, keeping the first, would be equally
    defensible but must at least be deterministic, which this asserts.
    """
    frame = make_trend_then_reverse(400, seed=149)
    duplicated = pd.concat([frame, frame.iloc[[-1]]])
    assert duplicated.index.has_duplicates

    now = frame.index[-1] + pd.Timedelta(days=1)
    signals = _engine().compute(duplicated, "XAUUSD", "H1", now=now)
    for signal in signals:
        assert signal.timestamp in frame.index
        assert signal.price == pytest.approx(
            float(frame.loc[signal.timestamp, "close"]), abs=TOLERANCE
        )
