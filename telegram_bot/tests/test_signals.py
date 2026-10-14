"""Tests for signal firing, cooldown, deduplication and symbol independence.

Every test that asserts on delivery pins the clock to :data:`ACTIVE_TS` rather
than calling ``utcnow()``. Quiet hours are real behaviour, so a wall-clock test
would silently stop working between 22:00 and 03:00 UTC.
"""

from __future__ import annotations

import dataclasses

import pytest

from telegram_bot.db import utcnow
from telegram_bot.tests.conftest import ACTIVE_TS, QUIET_TS, make_trending_frame

SYMBOLS = ("XAUUSD", "BTCUSD")
TIMEFRAMES = ("1m", "5m", "15m", "1h")


def _permissive(config):
    """A relaxed threshold, so these tests exercise delivery rather than scoring."""
    return dataclasses.replace(config, confidence_min=0.35)


def _scanner(db, config, market):
    from telegram_bot.scanner import Scanner

    return Scanner(db=db, config=_permissive(config), market=market, started_at=0.0)


def _set(market, symbol: str, timeframe: str) -> None:
    """Pin a trending frame whose newest bar is closed at the pinned clock."""
    from telegram_bot.timeframes import TIMEFRAME_SECONDS

    market.set_frame(
        symbol,
        timeframe,
        make_trending_frame(
            300, seconds=TIMEFRAME_SECONDS[timeframe], end_ts=ACTIVE_TS
        ),
    )


# --------------------------------------------------------------------------- #
# Signals fire per timeframe and per symbol
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("symbol", SYMBOLS)
@pytest.mark.parametrize("timeframe", TIMEFRAMES)
async def test_signal_can_fire_on_every_pair(
    db, config, market, symbol: str, timeframe: str
) -> None:
    """Every configured pair is scannable and can produce a signal."""
    _set(market, symbol, timeframe)
    scanner = _scanner(db, config, market)

    result = await scanner.scan(symbol=symbol, timeframe=timeframe, now=ACTIVE_TS)

    assert result.errors == {}, f"{symbol} {timeframe}: {result.errors}"
    assert result.computed, f"{symbol} {timeframe} produced no signal"


async def test_symbols_are_independent(db, config, market) -> None:
    """One symbol's cooldown or failure must not touch the other."""
    _set(market, "XAUUSD", "5m")
    _set(market, "BTCUSD", "5m")
    market.fail("BTCUSD", "5m")

    scanner = _scanner(db, config, market)
    result = await scanner.scan(timeframe="5m", now=ACTIVE_TS)

    assert any(s.symbol == "XAUUSD" for s in result.computed)
    assert not any(s.symbol == "BTCUSD" for s in result.computed)
    assert any("BTCUSD" in key for key in result.errors)


async def test_one_symbol_failing_does_not_abandon_the_pass(db, config, market) -> None:
    """A fetch error on one pair must not stop the remaining seven."""
    for symbol in SYMBOLS:
        for timeframe in TIMEFRAMES:
            _set(market, symbol, timeframe)
    market.fail("XAUUSD", "1m")

    scanner = _scanner(db, config, market)
    result = await scanner.scan(now=ACTIVE_TS)

    assert len(result.computed) == 7, "one failure cost more than one pair"
    assert len(result.errors) == 1


# --------------------------------------------------------------------------- #
# Cooldown
# --------------------------------------------------------------------------- #


async def test_cooldown_suppresses_a_repeat(db, config, market) -> None:
    """A second, genuinely new signal inside the cooldown is withheld.

    The frame is advanced so the second scan anchors to a different bar. Re-scanning
    the *same* bar is a different path — deduplication — and asserting on it here
    would be testing the wrong mechanism.
    """
    _set(market, "XAUUSD", "5m")
    scanner = _scanner(db, config, market)

    first = await scanner.scan(symbol="XAUUSD", timeframe="5m", now=ACTIVE_TS)
    assert first.delivered, "the first signal for a pair must actually be sent"

    # A new closed bar, but only 10 minutes later — inside the 5m cooldown of 30.
    later = ACTIVE_TS + 600
    market.set_frame(
        "XAUUSD", "5m", make_trending_frame(300, seconds=300, end_ts=later)
    )
    second = await scanner.scan(symbol="XAUUSD", timeframe="5m", now=later)

    assert second.computed, "the new bar should still produce a signal"
    assert second.stored, "a suppressed signal is still recorded"
    assert second.delivered == []
    assert any("cooldown" in reason for reason in second.suppressed.values())


async def test_rescanning_the_same_bar_is_a_no_op(db, config, market) -> None:
    """A repeat scan of one bar stores nothing further and sends nothing."""
    _set(market, "XAUUSD", "5m")
    scanner = _scanner(db, config, market)

    first = await scanner.scan(symbol="XAUUSD", timeframe="5m", now=ACTIVE_TS)
    before = db.signal_count_since(0)

    second = await scanner.scan(symbol="XAUUSD", timeframe="5m", now=ACTIVE_TS)

    assert first.delivered
    assert second.delivered == []
    assert second.stored == [], "the same bar was stored twice"
    assert db.signal_count_since(0) == before


@pytest.mark.parametrize("timeframe", TIMEFRAMES)
async def test_each_timeframe_has_its_own_cooldown(
    db, config, market, timeframe: str
) -> None:
    """A cooldown on one timeframe must not suppress a different one."""
    _set(market, "XAUUSD", timeframe)
    scanner = _scanner(db, config, market)

    await scanner.scan(symbol="XAUUSD", timeframe=timeframe, now=ACTIVE_TS)
    other = "5m" if timeframe != "5m" else "1m"

    _set(market, "XAUUSD", other)
    result = await scanner.scan(symbol="XAUUSD", timeframe=other, now=ACTIVE_TS)
    assert result.delivered, f"{timeframe}'s cooldown suppressed {other}"


async def test_hourly_cap_suppresses_bursts(db, config, market) -> None:
    """After the per-hour cap, further signals are computed but withheld."""
    _set(market, "XAUUSD", "1m")
    scanner = _scanner(db, config, market)

    delivered = 0
    for step in range(8):
        # Advance past the 1m cooldown each time so cooldown is not what stops it.
        result = await scanner.scan(
            symbol="XAUUSD", timeframe="1m", now=ACTIVE_TS + step * 20 * 60
        )
        delivered += len(result.delivered)

    assert delivered <= 4, f"hourly cap breached: {delivered} delivered"


async def test_quiet_hours_suppress_delivery(db, config, market) -> None:
    """Quiet hours withhold delivery but still record the signal."""
    # The frame must end at the quiet moment, or the engine would have no closed
    # bar to anchor to and there would be nothing to suppress.
    market.set_frame(
        "XAUUSD", "5m", make_trending_frame(300, seconds=300, end_ts=QUIET_TS)
    )
    scanner = _scanner(db, config, market)

    result = await scanner.scan(symbol="XAUUSD", timeframe="5m", now=QUIET_TS)

    assert result.computed, "the signal should still be computed"
    assert result.delivered == []
    assert any("quiet" in reason for reason in result.suppressed.values())
    assert db.signal_count_since(0) > 0, "the signal must still be recorded"


async def test_signals_outside_quiet_hours_are_delivered(db, config, market) -> None:
    """The same frame, scanned one minute before 14:00 UTC, is delivered."""
    _set(market, "XAUUSD", "5m")
    scanner = _scanner(db, config, market)

    result = await scanner.scan(symbol="XAUUSD", timeframe="5m", now=ACTIVE_TS)
    assert result.delivered


# --------------------------------------------------------------------------- #
# No duplicates
# --------------------------------------------------------------------------- #


async def test_the_same_bar_is_never_stored_twice(db, config, market) -> None:
    """Repeated scans of one bar must not produce duplicate rows."""
    _set(market, "XAUUSD", "5m")
    scanner = _scanner(db, config, market)

    for _ in range(5):
        await scanner.scan(symbol="XAUUSD", timeframe="5m", now=ACTIVE_TS)

    rows = db.signals_in_range(0, ACTIVE_TS + 10_000, symbol="XAUUSD")
    keys = [(r.symbol, r.timeframe, r.timestamp, r.action) for r in rows]
    assert len(keys) == len(set(keys)), "duplicate rows stored for the same bar"


async def test_a_restart_does_not_re_announce_a_bar(db, config, market) -> None:
    """Simulates a restart: a fresh scanner over the same data stores nothing new."""
    _set(market, "XAUUSD", "5m")

    first = _scanner(db, config, market)
    await first.scan(symbol="XAUUSD", timeframe="5m", now=ACTIVE_TS)
    before = db.signal_count_since(0)

    second = _scanner(db, config, market)
    await second.scan(symbol="XAUUSD", timeframe="5m", now=ACTIVE_TS)

    assert db.signal_count_since(0) == before


async def test_database_rejects_a_duplicate_row_directly(db) -> None:
    """The UNIQUE constraint, not application logic, is the guarantee."""
    from telegram_bot.engine import Signal
    from telegram_bot.orderflow import OrderFlowSnapshot

    now = utcnow()
    snapshot = OrderFlowSnapshot(
        "XAUUSD", "5m", 100.0, 200.0, "rising", None, 1.3, False, 1.0, "proxy", now
    )
    record = Signal(
        symbol="XAUUSD",
        timeframe="5m",
        bar_ts=now,
        action="BUY",
        entry=100.0,
        sl=99.0,
        tp1=102.0,
        tp2=104.0,
        confidence=0.8,
        layers={"trend": 0.8},
        order_flow=snapshot,
        reason="test",
    ).to_record(sent_at=now)

    assert db.save_signal(record) is not None
    assert db.save_signal(record) is None, "the unique constraint did not reject the duplicate"


# --------------------------------------------------------------------------- #
# Outcomes
# --------------------------------------------------------------------------- #


def test_a_signal_is_a_win_when_tp1_is_reached() -> None:
    from telegram_bot.engine import Signal, update_signal_outcome
    from telegram_bot.orderflow import OrderFlowSnapshot

    now = utcnow()
    signal = Signal(
        symbol="XAUUSD",
        timeframe="5m",
        bar_ts=now,
        action="BUY",
        entry=100.0,
        sl=99.0,
        tp1=102.0,
        tp2=104.0,
        confidence=0.8,
        layers={},
        order_flow=OrderFlowSnapshot("XAUUSD", "5m", 1.0, 1.0, "rising", None, 1.0, False, 1.0, "proxy", now),
        reason="test",
    )
    assert update_signal_outcome(signal, high=103.0, low=99.8) == "win"


def test_a_signal_is_a_loss_when_the_stop_is_hit() -> None:
    from telegram_bot.engine import Signal, update_signal_outcome
    from telegram_bot.orderflow import OrderFlowSnapshot

    now = utcnow()
    signal = Signal(
        symbol="XAUUSD",
        timeframe="5m",
        bar_ts=now,
        action="BUY",
        entry=100.0,
        sl=99.0,
        tp1=102.0,
        tp2=104.0,
        confidence=0.8,
        layers={},
        order_flow=OrderFlowSnapshot("XAUUSD", "5m", 1.0, 1.0, "rising", None, 1.0, False, 1.0, "proxy", now),
        reason="test",
    )
    assert update_signal_outcome(signal, high=100.5, low=98.5) == "loss"


def test_an_ambiguous_bar_is_scored_as_a_loss() -> None:
    """When stop and target are both inside one bar, the stop wins.

    The ordering is unknowable from OHLC, and assuming the favourable one would
    inflate every win rate the bot reports.
    """
    from telegram_bot.engine import Signal, update_signal_outcome
    from telegram_bot.orderflow import OrderFlowSnapshot

    now = utcnow()
    signal = Signal(
        symbol="XAUUSD",
        timeframe="5m",
        bar_ts=now,
        action="BUY",
        entry=100.0,
        sl=99.0,
        tp1=102.0,
        tp2=104.0,
        confidence=0.8,
        layers={},
        order_flow=OrderFlowSnapshot("XAUUSD", "5m", 1.0, 1.0, "rising", None, 1.0, False, 1.0, "proxy", now),
        reason="test",
    )
    # This bar spans the entry, the stop and the target.
    assert update_signal_outcome(signal, high=103.0, low=98.0) == "loss"


def test_a_signal_stays_open_until_a_level_is_reached() -> None:
    from telegram_bot.engine import Signal, update_signal_outcome
    from telegram_bot.orderflow import OrderFlowSnapshot

    now = utcnow()
    signal = Signal(
        symbol="XAUUSD",
        timeframe="5m",
        bar_ts=now,
        action="BUY",
        entry=100.0,
        sl=99.0,
        tp1=102.0,
        tp2=104.0,
        confidence=0.8,
        layers={},
        order_flow=OrderFlowSnapshot("XAUUSD", "5m", 1.0, 1.0, "rising", None, 1.0, False, 1.0, "proxy", now),
        reason="test",
    )
    assert update_signal_outcome(signal, high=100.4, low=99.6) is None


def test_risk_reward_is_measured_against_tp2() -> None:
    """Matches the required format, which shows 1:2.0 where TP1/risk is 1.0."""
    from telegram_bot.engine import Signal
    from telegram_bot.orderflow import OrderFlowSnapshot

    now = utcnow()
    signal = Signal(
        symbol="XAUUSD",
        timeframe="5m",
        bar_ts=now,
        action="BUY",
        entry=4156.23,
        sl=4132.10,
        tp1=4180.36,
        tp2=4204.49,
        confidence=0.72,
        layers={},
        order_flow=OrderFlowSnapshot("XAUUSD", "5m", 1.0, 1.0, "rising", None, 1.0, False, 1.0, "proxy", now),
        reason="test",
    )
    assert signal.risk_reward == pytest.approx(2.0, abs=0.01)


# --------------------------------------------------------------------------- #
# Signal geometry
# --------------------------------------------------------------------------- #


async def test_signal_levels_are_ordered_around_the_entry(db, config, market) -> None:
    _set(market, "XAUUSD", "5m")
    scanner = _scanner(db, config, market)
    result = await scanner.scan(symbol="XAUUSD", timeframe="5m", now=ACTIVE_TS)

    assert result.computed
    for signal in result.computed:
        if signal.action == "BUY":
            assert signal.sl < signal.entry < signal.tp1 < signal.tp2
        else:
            assert signal.sl > signal.entry > signal.tp1 > signal.tp2


async def test_a_scan_result_summarises_counts(db, config, market) -> None:
    _set(market, "XAUUSD", "5m")
    scanner = _scanner(db, config, market)
    result = await scanner.scan(symbol="XAUUSD", timeframe="5m", now=ACTIVE_TS)

    summary = result.summary()
    assert summary["computed"] == len(result.computed)
    assert summary["delivered"] == len(result.delivered)
    assert set(summary) == {"computed", "delivered", "stored", "confluences", "suppressed", "errors"}
