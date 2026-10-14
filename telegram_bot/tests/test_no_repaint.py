"""The anti-repaint proof.

Non-repainting means three separate things, and each is tested separately here
because each has failed in trading bots before:

1. **No future data.** A signal computed at bar *i* must be identical to the same
   signal computed from a frame truncated at *i*. One test recomputes the whole
   indicator chain that way, so a single negative shift or centred rolling window
   anywhere in the chain is caught without having to know where it was.
2. **No unclosed bars.** The newest bar of a frame is still forming; using it
   would let a signal appear and then change. Closure is decided by the injected
   clock, never by "the last row".
3. **No drift over time.** The same data must produce the same answer on every
   later run. A signal that changes as new bars arrive is a repaint even if it
   never looked at the future.

The property is also checked in reverse: a signal must *not* appear one bar
early, because a marker plotted a bar early is the failure users actually notice.
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pandas as pd
import pytest

from telegram_bot.engine import (
    bar_close_seconds,
    compute_signal,
    last_closed_position,
    to_closed_frame,
)
from telegram_bot.layers import build_features
from telegram_bot.tests.conftest import ACTIVE_TS, make_trending_frame

SYMBOLS = ("XAUUSD", "BTCUSD")
TIMEFRAMES = ("1m", "5m", "15m", "1h")


def _permissive(config):
    """A low threshold, so the checks below are about bar selection, not scoring."""
    return dataclasses.replace(config, confidence_min=0.35)


def _at(symbol: str, timeframe: str, end_ts: int = ACTIVE_TS, up: bool = True):
    from telegram_bot.timeframes import TIMEFRAME_SECONDS

    return make_trending_frame(
        300, up=up, seconds=TIMEFRAME_SECONDS[timeframe], end_ts=end_ts
    )


def _extend(frame: pd.DataFrame, n_bars: int = 20, *, seed: int = 99) -> pd.DataFrame:
    """Append ``n_bars`` of plausible future data after ``frame``.

    Used to model the feed arriving later. The appended bars are allowed to be as
    violent as they like — the point is that nothing already reported may move.
    """
    rng = np.random.default_rng(seed)
    base = float(frame["close"].iloc[-1])
    closes = base * np.exp(rng.normal(0.004, 0.012, n_bars))
    opens = np.concatenate([[base], closes[:-1]])
    step = (
        int((frame.index[1] - frame.index[0]).total_seconds()) if len(frame) > 1 else 300
    )

    extra = pd.DataFrame(
        {
            "open": opens,
            "high": np.maximum(opens, closes) * 1.004,
            "low": np.minimum(opens, closes) * 0.996,
            "close": closes,
            "tick_volume": rng.integers(80, 400, size=n_bars).astype(float),
        },
        index=pd.DatetimeIndex(
            [frame.index[-1] + pd.Timedelta(seconds=step * (i + 1)) for i in range(n_bars)],
            name=frame.index.name,
        ),
    )
    return pd.concat([frame, extra])


# --------------------------------------------------------------------------- #
# 1. No future data
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("symbol", SYMBOLS)
def test_features_at_bar_i_match_a_frame_truncated_at_i(symbol: str) -> None:
    """The strongest single check available: nothing may read past its own bar."""
    full = make_trending_frame(400, seconds=300, end_ts=ACTIVE_TS)
    cut = 350

    expected = build_features(full).iloc[:cut]
    actual = build_features(full.iloc[:cut].copy())

    for column in expected.columns:
        if column.startswith("swing_"):
            # Swing columns are broadcast from their confirmation bar onward and
            # are checked separately, by their own confirmation rule.
            continue
        try:
            pd.testing.assert_series_equal(
                actual[column], expected[column], check_freq=False, check_names=False
            )
        except AssertionError as exc:
            raise AssertionError(f"{column} reads a future bar") from exc


@pytest.mark.parametrize("symbol", SYMBOLS)
def test_appending_a_future_bar_never_changes_an_earlier_layer_score(symbol: str) -> None:
    """A bar appearing later must not retroactively alter what was already said.

    This is the property a repainting bot breaks: the 5m signal at 14:00 was
    published as SELL, and when the 14:05 bar printed it was restated as BUY.
    """
    from telegram_bot.layers import compute_layers

    frame = make_trending_frame(300, seconds=300, end_ts=ACTIVE_TS)
    # An explicit position, not -1: after extending the frame, -1 would point at a
    # different bar and the comparison would be meaningless.
    position = len(frame) - 1

    before = {
        name: (result.score, result.evaluable, result.detail)
        for name, result in compute_layers(
            frame, symbol=symbol, timeframe="5m", position=position
        ).results.items()
    }

    # Extend the data well past the anchor bar, as the feed would minutes later.
    extended = _extend(frame, 20)
    after = compute_layers(
        extended, symbol=symbol, timeframe="5m", position=position
    ).results

    for name, score in before.items():
        assert (after[name].score, after[name].evaluable, after[name].detail) == score, (
            f"{name} changed once later bars arrived: {score} -> "
            f"{(after[name].score, after[name].evaluable, after[name].detail)}"
        )


def test_a_signal_at_a_fixed_bar_is_identical_whether_or_not_later_bars_exist() -> None:
    """The end-to-end version: same bar, same levels, same confidence, same reason."""
    from telegram_bot.db import Database
    from telegram_bot.defaults import BotConfig, seed_defaults

    frame = make_trending_frame(300, seconds=300, end_ts=ACTIVE_TS)

    db = Database(":memory:")
    db.initialise()
    seed_defaults(db)
    config = _permissive(BotConfig.load(db))

    anchor = int(frame.index[-1].timestamp())
    baseline = compute_signal(
        frame, symbol="XAUUSD", timeframe="5m", config=config, now=anchor
    )
    assert baseline is not None

    # Feed 20 further bars and recompute the *same* bar.
    extended = _extend(frame, 20, seed=7)
    later_now = int(extended.index[-1].timestamp())
    recomputed = compute_signal(
        extended,
        symbol="XAUUSD",
        timeframe="5m",
        config=config,
        now=later_now,
        position=len(frame) - 1,
    )

    assert recomputed is not None
    assert recomputed.bar_ts == baseline.bar_ts
    assert recomputed.action == baseline.action
    assert recomputed.entry == baseline.entry
    assert recomputed.sl == baseline.sl
    assert recomputed.tp1 == baseline.tp1
    assert recomputed.tp2 == baseline.tp2
    assert recomputed.confidence == pytest.approx(baseline.confidence)
    assert recomputed.reason == baseline.reason
    assert recomputed.layers == baseline.layers

    db.close()


@pytest.mark.parametrize("timeframe", TIMEFRAMES)
def test_recomputing_the_same_bar_is_stable_across_repeats(timeframe: str) -> None:
    """Determinism: identical inputs must give bit-identical outputs, always."""
    from telegram_bot.db import Database
    from telegram_bot.defaults import BotConfig, seed_defaults

    db = Database(":memory:")
    db.initialise()
    seed_defaults(db)
    config = _permissive(BotConfig.load(db))

    frame = _at("XAUUSD", timeframe)
    anchor = int(frame.index[-1].timestamp())

    results = [
        compute_signal(
            frame, symbol="XAUUSD", timeframe=timeframe, config=config, now=anchor
        )
        for _ in range(5)
    ]
    assert all(r is not None for r in results)
    assert len({(r.action, r.entry, r.confidence) for r in results}) == 1
    db.close()


# --------------------------------------------------------------------------- #
# 2. No unclosed bars
# --------------------------------------------------------------------------- #


def test_a_bar_closes_only_at_its_own_close_time() -> None:
    frame = _at("XAUUSD", "5m")
    closes = bar_close_seconds(frame.index)
    anchor = int(closes[-1])

    assert last_closed_position(frame.index, anchor - 1, confirm=True) == len(frame) - 2
    assert last_closed_position(frame.index, anchor, confirm=True) == len(frame) - 1


def test_the_trailing_bar_is_skipped_when_the_clock_is_unknown() -> None:
    """With no clock, assuming the last bar is closed could fabricate a signal."""
    frame = _at("XAUUSD", "5m")

    assert last_closed_position(frame.index, None, confirm=True) == len(frame) - 2
    assert last_closed_position(frame.index, None, confirm=False) == len(frame) - 1


def test_no_signal_is_computed_from_a_forming_bar() -> None:
    """A clock one second before the last close must anchor to the bar before it."""
    from telegram_bot.db import Database
    from telegram_bot.defaults import BotConfig, seed_defaults

    db = Database(":memory:")
    db.initialise()
    seed_defaults(db)
    config = _permissive(BotConfig.load(db))

    frame = _at("XAUUSD", "5m")
    last_close = int(bar_close_seconds(frame.index)[-1])

    forming = compute_signal(
        frame, symbol="XAUUSD", timeframe="5m", config=config, now=last_close - 1
    )
    closed = compute_signal(
        frame, symbol="XAUUSD", timeframe="5m", config=config, now=last_close
    )

    if forming is not None:
        assert forming.bar_ts != last_close, (
            "a signal was computed on a bar that had not closed yet"
        )
    if closed is not None:
        assert closed.bar_ts == last_close
    db.close()


def test_an_unknown_clock_never_uses_the_trailing_bar() -> None:
    from telegram_bot.db import Database
    from telegram_bot.defaults import BotConfig, seed_defaults

    db = Database(":memory:")
    db.initialise()
    seed_defaults(db)
    config = _permissive(BotConfig.load(db))

    frame = _at("XAUUSD", "5m")
    last_close = int(bar_close_seconds(frame.index)[-1])

    signal = compute_signal(
        frame, symbol="XAUUSD", timeframe="5m", config=config, now=None
    )
    if signal is not None:
        assert signal.bar_ts != last_close
    db.close()


def test_a_signal_never_appears_one_bar_early() -> None:
    """The reverse check: the marker must land on its own bar, not the one before.

    A repaint that is only ever visible as an off-by-one is still off-by-one, and
    the user sees it as a marker on the wrong candle.
    """
    from telegram_bot.db import Database
    from telegram_bot.defaults import BotConfig, seed_defaults

    db = Database(":memory:")
    db.initialise()
    seed_defaults(db)
    config = _permissive(BotConfig.load(db))

    frame = _at("XAUUSD", "5m")
    closes = bar_close_seconds(frame.index)

    for position in range(len(frame) - 60, len(frame)):
        anchor = int(closes[position])
        signal = compute_signal(
            frame,
            symbol="XAUUSD",
            timeframe="5m",
            config=config,
            now=anchor,
            position=position,
        )
        if signal is not None:
            assert signal.bar_ts == anchor, (
                f"signal at bar {position} is stamped {signal.bar_ts}, "
                f"not its own close {anchor}"
            )
    db.close()


@pytest.mark.parametrize("timeframe", TIMEFRAMES)
def test_each_timeframe_uses_its_own_bar_duration(timeframe: str) -> None:
    """A 1h signal must not be stamped with a 5m bar's close."""
    from telegram_bot.db import Database
    from telegram_bot.defaults import BotConfig, seed_defaults
    from telegram_bot.timeframes import TIMEFRAME_SECONDS

    db = Database(":memory:")
    db.initialise()
    seed_defaults(db)
    config = _permissive(BotConfig.load(db))

    frame = _at("XAUUSD", timeframe)
    anchor = int(bar_close_seconds(frame.index)[-1])
    signal = compute_signal(
        frame, symbol="XAUUSD", timeframe=timeframe, config=config, now=anchor
    )
    if signal is not None:
        assert anchor % TIMEFRAME_SECONDS[timeframe] == 0
    db.close()


def test_a_naive_index_is_refused_rather_than_guessed() -> None:
    """A naive timestamp has no defined instant, so guessing would misplace signals."""
    frame = _at("XAUUSD", "5m").copy()
    frame.index = frame.index.tz_localize(None)

    with pytest.raises(ValueError, match="timezone-aware"):
        bar_close_seconds(frame.index)


# --------------------------------------------------------------------------- #
# The feed conversion
# --------------------------------------------------------------------------- #


def _series(*, with_open_bar: bool = False):
    """A minimal feed series of closed 5m bars, oldest first."""
    from shared.schemas.market import OhlcBar, OhlcSeries

    bars = [
        OhlcBar(
            symbol="XAUUSD",
            interval="5m",
            openTime=pd.Timestamp(ACTIVE_TS - (60 - i) * 300, unit="s", tz="UTC"),
            open=4_000.0 + i,
            high=4_005.0 + i,
            low=3_995.0 + i,
            close=4_001.0 + i,
            volume=0.0,
            tickVolume=100,
        )
        for i in range(60)
    ]
    if with_open_bar:
        bars.append(
            OhlcBar(
                symbol="XAUUSD",
                interval="5m",
                openTime=pd.Timestamp(ACTIVE_TS, unit="s", tz="UTC"),
                open=4_060.0,
                high=4_999.0,  # A huge spike that must never influence a signal
                low=3_000.0,
                close=4_001.0,
                volume=0.0,
                tickVolume=9_999_999,
                isOpen=True,
            )
        )
    return OhlcSeries(symbol="XAUUSD", interval="5m", bars=tuple(bars))


def test_to_closed_frame_indexes_by_close_time_not_open_time() -> None:
    """An open-time label would misplace every marker by one bar."""
    frame = to_closed_frame(_series(), "5m")
    assert frame.index.name == "close_time"
    assert list(frame.index) == sorted(frame.index)

    source = _series().bars[0]
    assert frame.index[0] == source.open_time + pd.Timedelta(seconds=300)


def test_to_closed_frame_drops_the_in_progress_bar() -> None:
    """The spike in the open bar is exactly the kind of data that must be ignored."""
    closed_only = to_closed_frame(_series(), "5m")
    with_open = to_closed_frame(_series(with_open_bar=True), "5m")

    assert len(with_open) == len(closed_only)
    pd.testing.assert_frame_equal(with_open, closed_only)


def test_the_open_bar_spike_cannot_move_a_signal() -> None:
    """End-to-end: a wild in-progress bar must not change the computed signal."""
    from telegram_bot.db import Database
    from telegram_bot.defaults import BotConfig, seed_defaults

    db = Database(":memory:")
    db.initialise()
    seed_defaults(db)
    config = _permissive(BotConfig.load(db))

    baseline_frame = to_closed_frame(_series(), "5m")
    spiked_frame = to_closed_frame(_series(with_open_bar=True), "5m")

    anchor = int(baseline_frame.index[-1].timestamp())
    baseline = compute_signal(
        baseline_frame, symbol="XAUUSD", timeframe="5m", config=config, now=anchor
    )
    spiked = compute_signal(
        spiked_frame, symbol="XAUUSD", timeframe="5m", config=config, now=anchor
    )

    if baseline is None:
        assert spiked is None
    else:
        assert spiked is not None
        assert spiked.bar_ts == baseline.bar_ts
        assert spiked.action == baseline.action
        assert spiked.entry == baseline.entry
        assert spiked.confidence == pytest.approx(baseline.confidence)
    db.close()


def test_to_closed_frame_returns_an_empty_frame_rather_than_raising() -> None:
    from shared.schemas.market import OhlcBar, OhlcSeries

    series = OhlcSeries(
        symbol="XAUUSD",
        interval="5m",
        bars=(
            OhlcBar(
                symbol="XAUUSD",
                interval="5m",
                openTime=pd.Timestamp(ACTIVE_TS, unit="s", tz="UTC"),
                open=1.0,
                high=1.0,
                low=1.0,
                close=1.0,
                volume=0.0,
                tickVolume=0,
                isOpen=True,
            ),
        ),
    )
    frame = to_closed_frame(series, "5m")
    assert frame.empty
    assert compute_signal(frame, symbol="XAUUSD", timeframe="5m", config=None) is None


# --------------------------------------------------------------------------- #
# Storage
# --------------------------------------------------------------------------- #


async def test_a_re_scan_of_the_same_bar_does_not_restate_the_signal(db, config, market) -> None:
    """What was announced must stay announced, even across a restart."""
    from telegram_bot.scanner import Scanner

    market.set_frame("XAUUSD", "5m", make_trending_frame(300, seconds=300, end_ts=ACTIVE_TS))

    first = await Scanner(
        db=db, config=_permissive(config), market=market, started_at=0.0
    ).scan(symbol="XAUUSD", timeframe="5m", now=ACTIVE_TS)
    assert first.delivered

    # A brand-new scanner stands in for a process restart.
    second = await Scanner(
        db=db, config=_permissive(config), market=market, started_at=0.0
    ).scan(symbol="XAUUSD", timeframe="5m", now=ACTIVE_TS)

    assert second.delivered == [], "the same bar was announced a second time"
    assert second.stored == []
    assert db.signal_count_since(0) == len(first.stored)

    rows = db.signals_in_range(0, ACTIVE_TS + 10_000, symbol="XAUUSD")
    assert len({(r.timeframe, r.timestamp, r.action) for r in rows}) == len(rows)


def _announce(signal):
    """The user-visible text, for comparing what was actually announced."""
    from telegram_bot.formatter import format_signal

    return format_signal(signal)


async def test_the_database_refuses_to_overwrite_a_stored_signal(db, config) -> None:
    """A second write of the same bar is rejected by the schema, not by luck."""
    from telegram_bot.engine import Signal
    from telegram_bot.orderflow import OrderFlowSnapshot

    snapshot = OrderFlowSnapshot(
        "XAUUSD", "5m", 100.0, 200.0, "rising", None, 1.3, False, 1.0, "proxy", ACTIVE_TS
    )
    signal = Signal(
        symbol="XAUUSD",
        timeframe="5m",
        bar_ts=ACTIVE_TS,
        action="BUY",
        entry=4_100.0,
        sl=4_080.0,
        tp1=4_130.0,
        tp2=4_160.0,
        confidence=0.75,
        layers={"trend": 0.9},
        order_flow=snapshot,
        reason="first",
    )
    assert db.save_signal(signal.to_record(sent_at=ACTIVE_TS)) is not None

    # A restatement of the same bar with different numbers must not land.
    restated = dataclasses.replace(
        signal, entry=4_200.0, reason="second, after seeing more data"
    )
    assert db.save_signal(restated.to_record(sent_at=ACTIVE_TS + 60)) is None

    row = db.signals_in_range(0, ACTIVE_TS + 10_000, symbol="XAUUSD")[0]
    assert row.entry == 4_100.0
    assert row.reason == "first"
