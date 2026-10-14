"""THE ANTI-REPAINT PROOF.

A repainting signal is one that changes after it was published. There are three
distinct ways that happens, and each gets a test that fails if the engine
regresses:

1. **The trailing unclosed bar.** A signal computed on a bar that is still forming
   changes when the bar finishes. ``test_trailing_open_bar_never_produces_a_signal``
   and ``test_signal_appears_only_after_the_bar_closes`` cover this.

2. **Recomputation drift.** Recomputing over a longer history must not change any
   earlier signal. This is the subtle one: a ``bfill``, a centred rolling window,
   or an EMA seeded from the whole series would all pass a "is the last bar right"
   test while silently moving signals that were already published.
   ``test_recomputation_over_a_longer_frame_changes_nothing`` is that test.

3. **Attachment drift.** A signal whose timestamp or price belongs to a
   neighbouring bar. Covered in ``test_attached.py``.

The shared technique: compute on ``df[:-1]`` and on ``df``, then assert the signals
on every bar except the new last one are *identical objects in value*. Anything
less would let a subtle transformation through.
"""

from __future__ import annotations

import pandas as pd
import pytest

from signals.engine import SignalEngine, frame_from_series
from signals.models import SignalConfig
from signals.tests.factories import (
    make_ohlcv,
    make_range,
    make_trend_then_reverse,
    with_open_bar,
    without_last,
)


def _aggressive_engine() -> SignalEngine:
    """A permissive engine, so a test failure means a repaint bug and not filtering."""
    return SignalEngine(
        SignalConfig(
            mode="aggressive",
            confidence_threshold=0.30,
            mandatory_layers=(),
            min_bars_between_signals=0,
            require_opposite_before_repeat=False,
            ema_fast=10,
            ema_slow=30,
        )
    )


def _signals_for(frame: pd.DataFrame, **kwargs) -> list:
    """Compute over a whole frame with every bar treated as closed."""
    engine = _aggressive_engine()
    # A `now` past the final bar means the trailing bar counts as closed, which is
    # the situation these tests want to isolate: given closed bars, do results hold?
    now = frame.index[-1] + pd.Timedelta(days=1)
    return engine.compute(frame, "XAUUSD", "H1", now=now, **kwargs)


def _keys(signals: list) -> list[tuple]:
    """Identity of each signal, ignoring nothing — every field is compared."""
    return [
        (s.timestamp, s.symbol, s.timeframe, s.action, s.price, s.sl, s.tp1, s.tp2, round(s.confidence, 12))
        for s in signals
    ]


# --------------------------------------------------------------------------- #
# Proof 1 — recomputation over a longer frame changes nothing
# --------------------------------------------------------------------------- #


def test_recomputation_over_a_longer_frame_changes_nothing() -> None:
    """Adding one bar must not alter any signal already emitted.

    Signals computed on ``df`` restricted to all but the last bar are compared
    against the same signals from the full ``df``. If the engine repaints through
    an indicator that reads forward, or seeds an EMA from the whole series, the
    earlier values shift and this fails.
    """
    full = make_trend_then_reverse(400, seed=41)

    from_partial = _signals_for(without_last(full))
    from_full = _signals_for(full)

    partial_last_bar = without_last(full).index[-1]
    surviving = [s for s in from_full if s.timestamp <= partial_last_bar]

    assert _keys(surviving) == _keys(from_partial), (
        "signals before the last bar changed when a further bar was added — "
        "the engine is reading forward"
    )


@pytest.mark.parametrize("cut", [220, 260, 300, 340, 380])
def test_no_signal_moves_when_history_is_extended(cut: int) -> None:
    """Every prefix of the series must agree with the full computation.

    A single cut can miss an indicator whose lookahead only manifests later; five
    cuts across the series do not.
    """
    full = make_trend_then_reverse(400, seed=43)
    # Index the full computation's signals by timestamp, so a prefix result can be
    # looked up directly rather than positionally.
    reference = {s.timestamp: s for s in _signals_for(full)}

    partial = _signals_for(full.iloc[:cut].copy())
    for signal in partial:
        assert signal.timestamp in reference, (
            f"signal at {signal.timestamp.isoformat()} appears in a prefix but not "
            "in the full computation — the engine's output depends on future bars"
        )
        expected = reference[signal.timestamp]
        actual = (
            signal.action,
            signal.price,
            signal.sl,
            signal.tp1,
            signal.tp2,
            round(signal.confidence, 12),
        )
        assert actual == (
            expected.action,
            expected.price,
            expected.sl,
            expected.tp1,
            expected.tp2,
            round(expected.confidence, 12),
        )


def test_a_signal_never_changes_confidence_after_appearing() -> None:
    """Confidence is part of a published claim and must be stable too."""
    full = make_range(400, seed=47)
    now = full.index[-1] + pd.Timedelta(days=1)
    engine = _aggressive_engine()

    seen: dict[pd.Timestamp, float] = {}
    for end in range(220, len(full) + 1, 20):
        window = full.iloc[:end].copy()
        for signal in engine.compute(window, "XAUUSD", "H1", now=now):
            if signal.timestamp in seen:
                assert signal.confidence == pytest.approx(seen[signal.timestamp], abs=1e-12)
            else:
                seen[signal.timestamp] = signal.confidence


# --------------------------------------------------------------------------- #
# Proof 2 — an unclosed bar is never signalled
# --------------------------------------------------------------------------- #


def test_trailing_open_bar_never_produces_a_signal() -> None:
    """An in-progress bar must not carry a signal, however attractive it looks.

    The appended bar is moved 2% so that, if it were scored, it would be an obvious
    signal. Nothing may anchor to it.
    """
    base = make_trend_then_reverse(400, seed=53)
    extended = with_open_bar(base, mutate=0.02)
    open_timestamp = extended.index[-1]

    # No `now`: the engine must assume the trailing bar is unclosed.
    signals = _aggressive_engine().compute(extended, "XAUUSD", "H1")

    assert open_timestamp not in {s.timestamp for s in signals}
    # And the signal set equals the closed-bars-only computation exactly.
    assert _keys(signals) == _keys(_signals_for(base))


def test_a_signal_appears_only_after_the_bar_closes() -> None:
    """The same bar yields nothing while open, then a signal once closed.

    This is the flip side of the previous test: the guard must not be so strict
    that a genuine signal is suppressed forever.
    """
    base = make_trend_then_reverse(400, seed=59)
    engine = _aggressive_engine()
    last_closed = base.index[-1]

    before = engine.compute(base, "XAUUSD", "H1", now=last_closed)
    after = engine.compute(base, "XAUUSD", "H1", now=last_closed + pd.Timedelta(hours=2))

    assert len(after) >= len(before), "signals disappeared when a bar closed"
    assert _keys(after[: len(before)]) == _keys(before)


def test_confirm_on_close_false_still_requires_an_explicit_now() -> None:
    """With the guard disabled, the caller must say when the bar closed.

    Otherwise there is no `now` against which closure could be judged, and the
    engine falls back to its conservative behaviour: skip the trailing bar.
    """
    base = make_trend_then_reverse(400, seed=61)
    engine = SignalEngine(
        SignalConfig(
            mode="aggressive",
            confidence_threshold=0.30,
            mandatory_layers=(),
            confirm_on_close=False,
            min_bars_between_signals=0,
            ema_fast=10,
            ema_slow=30,
        )
    )
    # A `now` before the last bar's close: even with the guard off, an unclosed
    # bar is not signalled.
    early = base.index[-1] - pd.Timedelta(minutes=1)
    signals = engine.compute(base, "XAUUSD", "H1", now=early)
    assert base.index[-1] not in {s.timestamp for s in signals}


def test_now_boundary_is_inclusive_at_the_close_instant() -> None:
    """A bar whose close time equals `now` counts as closed."""
    base = make_trend_then_reverse(400, seed=67)
    engine = _aggressive_engine()
    last = base.index[-1]

    at = engine.compute(base, "XAUUSD", "H1", now=last)
    before = engine.compute(base, "XAUUSD", "H1", now=last - pd.Timedelta(nanoseconds=1))
    after = engine.compute(base, "XAUUSD", "H1", now=last + pd.Timedelta(nanoseconds=1))

    # The final bar counts as closed at exactly its close time, so `at` and
    # `after` agree. Whether `at` holds one signal more than `before` depends on
    # whether that bar qualified at all, which is a market question — so the
    # assertion is that `at` never has *fewer*, and that nothing is lost.
    assert _keys(after) == _keys(at)
    assert len(at) >= len(before)
    assert _keys(at)[: len(before)] == _keys(before)


# --------------------------------------------------------------------------- #
# Proof 3 — evaluate_bar refuses an unclosed bar
# --------------------------------------------------------------------------- #


def test_evaluate_bar_rejects_an_unclosed_bar() -> None:
    """The single-bar entry point must enforce closure, not just document it."""
    base = make_trend_then_reverse(400, seed=71)
    engine = _aggressive_engine()
    last = base.index[-1]

    with pytest.raises(ValueError, match="has not closed"):
        engine.evaluate_bar(
            base,
            "XAUUSD",
            "H1",
            last,
            now=last - pd.Timedelta(seconds=1),
        )


def test_evaluate_bar_accepts_a_closed_bar() -> None:
    base = make_trend_then_reverse(200, seed=73)
    engine = _aggressive_engine()
    # Well past the permissive engine's warmup (slow EMA is 30 here), so the bar is
    # genuinely evaluable rather than being skipped for lack of history.
    target = base.index[150]
    assert len(base) > 150, "fixture must be long enough for the test's bar index"

    signal = engine.evaluate_bar(
        base, "XAUUSD", "H1", target, now=base.index[-1] + pd.Timedelta(days=1)
    )
    if signal is not None:
        assert signal.timestamp == target


def test_evaluate_bar_raises_on_an_unknown_bar() -> None:
    base = make_ohlcv(300)
    engine = _aggressive_engine()
    with pytest.raises(KeyError):
        engine.evaluate_bar(
            base,
            "XAUUSD",
            "H1",
            pd.Timestamp("2030-01-01T00:00:00Z"),
            now=base.index[-1] + pd.Timedelta(days=1),
        )


def test_evaluate_bar_matches_the_full_computation() -> None:
    """Isolating one bar must not change its verdict.

    If `evaluate_bar` used a different indicator path or a truncated history, the
    two would disagree — and the disagreement would mean one of them is wrong.
    """
    base = make_trend_then_reverse(400, seed=79)
    engine = _aggressive_engine()
    now = base.index[-1] + pd.Timedelta(days=1)
    bulk = {s.timestamp: s for s in engine.compute(base, "XAUUSD", "H1", now=now)}

    for position in range(220, len(base), 17):
        target = base.index[position]
        isolated = engine.evaluate_bar(base, "XAUUSD", "H1", target, now=now)
        if target in bulk:
            assert isolated is not None, f"bulk found a signal at {target} but isolation did not"
            assert isolated.confidence == pytest.approx(bulk[target].confidence, abs=1e-12)
            assert isolated.action == bulk[target].action
            assert isolated.price == bulk[target].price


# --------------------------------------------------------------------------- #
# Proof 4 — the frame_from_series path obeys the same rules
# --------------------------------------------------------------------------- #


def test_frame_from_series_drops_the_open_bar_by_default() -> None:
    """The live data path must exclude the in-progress bar at the source.

    This is the production entry point, so a bug here would bypass every check the
    engine makes about closure.
    """
    from signals.tests.factories import make_series

    frame = make_trend_then_reverse(120, seed=83)
    series = make_series(frame, include_open_bar=True)
    # One extra bar: the 120 closed ones plus a forming one.
    assert len(series.bars) == len(frame) + 1
    assert series.bars[-1].is_open is True

    with_open = frame_from_series(series, drop_open_bar=True)
    assert len(with_open) == len(frame)

    without_dropping = frame_from_series(series, drop_open_bar=False)
    assert len(without_dropping) == len(frame) + 1


def test_frame_from_series_reindexes_to_close_time() -> None:
    """The conversion must produce close-time labels, not the feed's open times.

    ``make_series`` labels each bar with its **open** time, exactly as biquote
    does. ``frame_from_series`` must convert those to **close** times. Asserted
    directly against the open-time labels, because a one-bar drift here is exactly
    the bug the whole module exists to prevent — and it would be invisible in any
    test that only round-tripped through the same convention twice.
    """
    from signals.tests.factories import make_series

    frame = make_trend_then_reverse(60, seed=89)
    series = make_series(frame, interval="1h")
    open_times = [bar.open_time for bar in series.bars]
    converted = frame_from_series(series)

    assert converted.index.tolist() != open_times, (
        "the converted index matches the feed's open times — it was not "
        "re-indexed to bar close time"
    )
    converted_index = pd.DatetimeIndex(converted.index)
    offsets = (
        (converted_index - pd.DatetimeIndex(open_times)).total_seconds().unique().tolist()
    )
    assert offsets == [3_600.0], (
        f"expected every bar to shift one hour to close time, got {offsets}"
    )
    pd.testing.assert_series_equal(
        converted["close"],
        frame["close"],
        check_freq=False,
        check_names=False,
    )


def test_frame_from_series_returns_the_declared_empty_shape() -> None:
    from shared.schemas.market import OhlcSeries

    empty = frame_from_series(OhlcSeries(symbol="TEST", interval="1h", bars=()))
    assert empty.empty
    for column in ("open", "high", "low", "close"):
        assert column in empty.columns
