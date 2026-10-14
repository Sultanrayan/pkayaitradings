"""Tests for multi-timeframe confluence.

The rules that matter here:

* confluence is **within one symbol** — two symbols agreeing is not confluence;
* agreement is counted on **distinct timeframes**, so one timeframe firing three
  times is still one timeframe;
* a finer timeframe cannot be confluent with a coarser one, because the finer bar
  has not closed after the coarser one;
* confidence is **timeframe-weighted**, so a 1h agreement outweighs a 1m one.
"""

from __future__ import annotations

import dataclasses

import pytest

from telegram_bot.confluence import (
    Confluence,
    confluence_label,
    detect_confluence,
    detect_from_rows,
)
from telegram_bot.db import SignalRow
from telegram_bot.tests.conftest import ACTIVE_TS

TIMEFRAMES = ("1m", "5m", "15m", "1h")


def _row(
    *,
    symbol: str = "XAUUSD",
    timeframe: str = "5m",
    action: str = "BUY",
    timestamp: int = ACTIVE_TS,
    confidence: float = 0.7,
    row_id: int = 1,
) -> SignalRow:
    """A stored signal row, for testing the agreement logic without a database."""
    return SignalRow(
        id=row_id,
        symbol=symbol,
        timeframe=timeframe,
        timestamp=timestamp,
        action=action,
        entry=4_150.0,
        sl=4_130.0,
        tp1=4_170.0,
        tp2=4_190.0,
        confidence=confidence,
        layers={"trend": 0.8},
        order_flow=None,
        reason="test",
        is_confluence=False,
        confluence_tfs=(),
        sent_at=timestamp,
        outcome=None,
        closed_at=None,
        pnl_pct=None,
    )


# --------------------------------------------------------------------------- #
# Two agreeing timeframes are enough
# --------------------------------------------------------------------------- #


def test_two_agreeing_timeframes_confluence() -> None:
    rows = [_row(timeframe="5m"), _row(timeframe="15m", row_id=2)]
    confluence = detect_from_rows(rows, symbol="XAUUSD", action="BUY", timeframe="15m")
    assert confluence is not None
    assert confluence.timeframes == ("5m", "15m")
    assert confluence.action == "BUY"
    assert confluence.symbol == "XAUUSD"


def test_one_timeframe_alone_is_not_a_confluence() -> None:
    assert (
        detect_from_rows(
            [_row(timeframe="5m")], symbol="XAUUSD", action="BUY", timeframe="5m"
        )
        is None
    )


def test_disagreeing_timeframes_do_not_confluence() -> None:
    rows = [_row(timeframe="5m", action="BUY"), _row(timeframe="15m", action="SELL", row_id=2)]
    assert (
        detect_from_rows(rows, symbol="XAUUSD", action="BUY", timeframe="15m") is None
    )


def test_no_rows_is_not_a_confluence() -> None:
    assert (
        detect_from_rows([], symbol="XAUUSD", action="BUY", timeframe="5m") is None
    )


# --------------------------------------------------------------------------- #
# Counting is per timeframe, not per signal
# --------------------------------------------------------------------------- #


def test_repeat_signals_on_one_timeframe_count_once() -> None:
    """Three 5m signals are still one timeframe, so there is no confluence."""
    rows = [
        _row(timeframe="5m", timestamp=ACTIVE_TS - 600, row_id=1),
        _row(timeframe="5m", timestamp=ACTIVE_TS - 300, row_id=2),
        _row(timeframe="5m", timestamp=ACTIVE_TS, row_id=3),
    ]
    assert (
        detect_from_rows(rows, symbol="XAUUSD", action="BUY", timeframe="5m") is None
    )


def test_the_newest_signal_per_timeframe_is_used() -> None:
    rows = [
        _row(timeframe="5m", timestamp=ACTIVE_TS - 600, confidence=0.5, row_id=1),
        _row(timeframe="5m", timestamp=ACTIVE_TS, confidence=0.9, row_id=2),
        _row(timeframe="15m", timestamp=ACTIVE_TS - 300, confidence=0.7, row_id=3),
    ]
    confluence = detect_from_rows(rows, symbol="XAUUSD", action="BUY", timeframe="15m")
    assert confluence is not None
    five_minutes = next(m for m in confluence.members if m.timeframe == "5m")
    assert five_minutes.confidence == 0.9, "a stale 5m signal was preferred"


# --------------------------------------------------------------------------- #
# Symbol independence
# --------------------------------------------------------------------------- #


def test_confluence_never_crosses_symbols() -> None:
    """Gold buying and bitcoin selling are two facts, not one stronger fact."""
    rows = [
        _row(symbol="XAUUSD", timeframe="5m"),
        _row(symbol="BTCUSD", timeframe="15m", row_id=2),
    ]
    assert (
        detect_from_rows(rows, symbol="XAUUSD", action="BUY", timeframe="15m") is None
    )


def test_a_mismatched_symbol_row_is_ignored() -> None:
    rows = [
        _row(symbol="XAUUSD", timeframe="5m"),
        _row(symbol="ETHUSD", timeframe="15m", row_id=2),
    ]
    assert (
        detect_from_rows(rows, symbol="xauusd", action="BUY", timeframe="15m") is None
    )


def test_symbol_matching_is_case_insensitive() -> None:
    rows = [_row(symbol="XAUUSD", timeframe="5m"), _row(timeframe="15m", row_id=2)]
    confluence = detect_from_rows(rows, symbol="xauusd", action="BUY", timeframe="15m")
    assert confluence is not None
    assert confluence.symbol == "XAUUSD"


# --------------------------------------------------------------------------- #
# Direction
# --------------------------------------------------------------------------- #


def test_a_sell_confluence_is_recognised() -> None:
    rows = [
        _row(timeframe="5m", action="SELL"),
        _row(timeframe="15m", action="SELL", row_id=2),
    ]
    confluence = detect_from_rows(rows, symbol="XAUUSD", action="SELL", timeframe="15m")
    assert confluence is not None
    assert confluence.action == "SELL"


# --------------------------------------------------------------------------- #
# Timeframe ordering and weighting
# --------------------------------------------------------------------------- #


def test_members_are_ordered_finest_first() -> None:
    rows = [
        _row(timeframe="1h", row_id=1),
        _row(timeframe="1m", row_id=2),
        _row(timeframe="5m", row_id=3),
        _row(timeframe="15m", row_id=4),
    ]
    confluence = detect_from_rows(rows, symbol="XAUUSD", action="BUY", timeframe="1h")
    assert confluence is not None
    assert confluence.timeframes == ("1m", "5m", "15m", "1h")


def test_the_representative_is_the_finest_timeframe() -> None:
    """The finest bar has the tightest stop and the fastest confirmation."""
    rows = [
        _row(timeframe="1h", row_id=1),
        _row(timeframe="5m", row_id=2),
    ]
    confluence = detect_from_rows(rows, symbol="XAUUSD", action="BUY", timeframe="1h")
    assert confluence is not None
    assert confluence.representative.timeframe == "5m"
    assert confluence.representative is confluence.members[0]


def test_confidence_is_timeframe_weighted() -> None:
    """A high-confidence 1h agreement must outweigh a low one.

    Weighting is only observable when the members disagree: with equal
    confidences every weighting scheme returns the same mean, so the two groups
    below deliberately differ.
    """
    fine = [
        _row(timeframe="1m", confidence=0.4, row_id=1),
        _row(timeframe="5m", confidence=0.6, row_id=2),
    ]
    coarse = [
        _row(timeframe="15m", confidence=0.6, row_id=1),
        _row(timeframe="1h", confidence=1.0, row_id=2),
    ]
    fine_conf = detect_from_rows(fine, symbol="XAUUSD", action="BUY", timeframe="5m")
    coarse_conf = detect_from_rows(coarse, symbol="XAUUSD", action="BUY", timeframe="1h")
    assert fine_conf is not None
    assert coarse_conf is not None
    # Unweighted means would be 0.5 and 0.8; weighting lifts the coarse group further.
    assert coarse_conf.confidence > fine_conf.confidence
    # Both are weighted means, not the unweighted 0.5 / 0.8 a plain average gives.
    assert fine_conf.confidence == pytest.approx((0.4 * 60 + 0.6 * 300) / 360)
    assert coarse_conf.confidence == pytest.approx((0.6 * 900 + 1.0 * 3_600) / 4_500)


def test_equal_confidences_weigh_out_to_their_mean() -> None:
    """With equal members, weighting is a no-op — a useful sanity check."""
    confluence = detect_from_rows(
        [_row(timeframe="1m", confidence=0.7, row_id=1), _row(timeframe="1h", confidence=0.7, row_id=2)],
        symbol="XAUUSD",
        action="BUY",
        timeframe="1h",
    )
    assert confluence is not None
    assert confluence.confidence == pytest.approx(0.7)


def test_equal_confidence_weighs_out_to_that_confidence_plus_a_bonus() -> None:
    """A two-timeframe group carries no bonus; a three-timeframe group gets 0.03."""
    two = detect_from_rows(
        [_row(timeframe="5m", confidence=0.7), _row(timeframe="15m", confidence=0.7, row_id=2)],
        symbol="XAUUSD",
        action="BUY",
        timeframe="15m",
    )
    three = detect_from_rows(
        [
            _row(timeframe="1m", confidence=0.7, row_id=1),
            _row(timeframe="5m", confidence=0.7, row_id=2),
            _row(timeframe="15m", confidence=0.7, row_id=3),
        ],
        symbol="XAUUSD",
        action="BUY",
        timeframe="15m",
    )
    assert two is not None
    assert three is not None
    assert two.confidence == pytest.approx(0.7)
    assert three.confidence == pytest.approx(0.73)


def test_the_bonus_is_capped() -> None:
    """Four timeframes must not manufacture a 0.06 premium that five would."""
    four = detect_from_rows(
        [_row(timeframe=tf, confidence=0.7, row_id=i) for i, tf in enumerate(TIMEFRAMES)],
        symbol="XAUUSD",
        action="BUY",
        timeframe="1h",
    )
    assert four is not None
    assert four.confidence == pytest.approx(0.76)


def test_confidence_never_exceeds_one() -> None:
    rows = [_row(timeframe=tf, confidence=1.0, row_id=i) for i, tf in enumerate(TIMEFRAMES)]
    confluence = detect_from_rows(rows, symbol="XAUUSD", action="BUY", timeframe="1h")
    assert confluence is not None
    assert confluence.confidence <= 1.0


def test_a_higher_minimum_can_veto_a_confluence() -> None:
    rows = [_row(timeframe="5m"), _row(timeframe="15m", row_id=2)]
    assert (
        detect_from_rows(
            rows, symbol="XAUUSD", action="BUY", timeframe="15m", min_tfs=3
        )
        is None
    )


def test_minimum_below_two_is_raised_to_two() -> None:
    """One timeframe can never be a confluence, however the config is written."""
    rows = [_row(timeframe="5m")]
    assert (
        detect_from_rows(
            rows, symbol="XAUUSD", action="BUY", timeframe="5m", min_tfs=1
        )
        is None
    )


# --------------------------------------------------------------------------- #
# Window semantics, against a real database
# --------------------------------------------------------------------------- #


def _store(db, *, symbol: str, timeframe: str, action: str, timestamp: int, conf: float = 0.7):
    """Write a signal straight into the database for window tests."""
    from telegram_bot.orderflow import OrderFlowSnapshot

    snapshot = OrderFlowSnapshot(
        symbol, timeframe, 1.0, 1.0, "rising", None, 1.0, False, 1.0, "proxy", timestamp
    )
    from telegram_bot.engine import Signal

    record = Signal(
        symbol=symbol,
        timeframe=timeframe,
        bar_ts=timestamp,
        action=action,
        entry=4_150.0,
        sl=4_130.0,
        tp1=4_170.0,
        tp2=4_190.0,
        confidence=conf,
        layers={},
        order_flow=snapshot,
        reason="test",
    ).to_record(sent_at=timestamp)
    db.save_signal(record)


def test_confluence_detects_agreement_from_the_database(db, config) -> None:
    from telegram_bot.timeframes import bar_seconds

    _store(db, symbol="XAUUSD", timeframe="5m", action="BUY", timestamp=ACTIVE_TS - bar_seconds("5m"))
    _store(db, symbol="XAUUSD", timeframe="15m", action="BUY", timestamp=ACTIVE_TS)

    confluence = detect_confluence(
        db, symbol="XAUUSD", timeframe="15m", action="BUY", config=config, now_ts=ACTIVE_TS
    )
    assert confluence is not None
    assert set(confluence.timeframes) == {"5m", "15m"}


def test_a_signal_outside_the_window_does_not_count(db, config) -> None:
    from telegram_bot.timeframes import bar_seconds

    window = bar_seconds("15m") * config.confluence_window_candles
    _store(db, symbol="XAUUSD", timeframe="5m", action="BUY", timestamp=ACTIVE_TS - window - 600)
    _store(db, symbol="XAUUSD", timeframe="15m", action="BUY", timestamp=ACTIVE_TS)

    confluence = detect_confluence(
        db, symbol="XAUUSD", timeframe="15m", action="BUY", config=config, now_ts=ACTIVE_TS
    )
    assert confluence is None, "a stale 5m signal was counted into the window"


def test_a_finer_timeframe_is_not_eligible(db, config) -> None:
    """A 5m bar cannot be confluent with a 1h signal: it has not closed after it."""
    _store(db, symbol="XAUUSD", timeframe="1h", action="BUY", timestamp=ACTIVE_TS - 3_600)
    _store(db, symbol="XAUUSD", timeframe="5m", action="BUY", timestamp=ACTIVE_TS)

    confluence = detect_confluence(
        db, symbol="XAUUSD", timeframe="5m", action="BUY", config=config, now_ts=ACTIVE_TS
    )
    assert confluence is None


def test_coarser_timeframes_are_eligible(db, config) -> None:
    """A 1h signal may gather agreement from every shorter timeframe."""
    for offset, timeframe in ((300, "5m"), (900, "15m")):
        _store(db, symbol="XAUUSD", timeframe=timeframe, action="BUY", timestamp=ACTIVE_TS - offset)
    _store(db, symbol="XAUUSD", timeframe="1h", action="BUY", timestamp=ACTIVE_TS)

    confluence = detect_confluence(
        db, symbol="XAUUSD", timeframe="1h", action="BUY", config=config, now_ts=ACTIVE_TS
    )
    assert confluence is not None
    assert set(confluence.timeframes) == {"5m", "15m", "1h"}


def test_a_coarser_timeframe_is_never_pulled_into_a_finer_trigger(db, config) -> None:
    """A 15m signal cannot be confluent with a 1h one — the hour has not closed since."""
    _store(db, symbol="XAUUSD", timeframe="1h", action="BUY", timestamp=ACTIVE_TS - 1_800)
    _store(db, symbol="XAUUSD", timeframe="15m", action="BUY", timestamp=ACTIVE_TS)

    assert (
        detect_confluence(
            db, symbol="XAUUSD", timeframe="15m", action="BUY", config=config, now_ts=ACTIVE_TS
        )
        is None
    )


def test_opposite_direction_signals_do_not_join(db, config) -> None:
    _store(db, symbol="XAUUSD", timeframe="5m", action="SELL", timestamp=ACTIVE_TS - 300)
    _store(db, symbol="XAUUSD", timeframe="15m", action="BUY", timestamp=ACTIVE_TS)

    assert (
        detect_confluence(
            db, symbol="XAUUSD", timeframe="15m", action="BUY", config=config, now_ts=ACTIVE_TS
        )
        is None
    )


def test_another_symbols_signals_are_not_counted(db, config) -> None:
    _store(db, symbol="BTCUSD", timeframe="5m", action="BUY", timestamp=ACTIVE_TS - 300)
    _store(db, symbol="XAUUSD", timeframe="15m", action="BUY", timestamp=ACTIVE_TS)

    assert (
        detect_confluence(
            db, symbol="XAUUSD", timeframe="15m", action="BUY", config=config, now_ts=ACTIVE_TS
        )
        is None
    )


def test_disabling_confluence_in_config_suppresses_detection(db, config) -> None:
    _store(db, symbol="XAUUSD", timeframe="5m", action="BUY", timestamp=ACTIVE_TS - 300)
    _store(db, symbol="XAUUSD", timeframe="15m", action="BUY", timestamp=ACTIVE_TS)

    off = dataclasses.replace(config, confluence_enabled=False)
    assert (
        detect_confluence(
            db, symbol="XAUUSD", timeframe="15m", action="BUY", config=off, now_ts=ACTIVE_TS
        )
        is None
    )


def test_an_empty_database_yields_nothing(db, config) -> None:
    assert (
        detect_confluence(
            db, symbol="XAUUSD", timeframe="15m", action="BUY", config=config, now_ts=ACTIVE_TS
        )
        is None
    )


# --------------------------------------------------------------------------- #
# Presentation
# --------------------------------------------------------------------------- #


def test_the_label_uses_user_timeframe_names() -> None:
    assert confluence_label(("1m", "5m", "15m", "1h")) == "1mn + 5mn + 15mn + 1h"


def test_a_single_timeframe_label_is_just_that_name() -> None:
    assert confluence_label(("5m",)) == "5mn"


def test_an_unknown_timeframe_is_shown_unchanged() -> None:
    """Better a raw internal name than a crash on a value the map does not know."""
    assert confluence_label(("4h",)) == "4h"


def test_confluence_round_trips_to_a_summary_dict() -> None:
    rows = [_row(timeframe="5m"), _row(timeframe="15m", row_id=2)]
    confluence = detect_from_rows(rows, symbol="XAUUSD", action="BUY", timeframe="15m")
    assert confluence is not None

    summary = confluence.to_dict()
    assert summary["symbol"] == "XAUUSD"
    assert summary["action"] == "BUY"
    assert summary["timeframes"] == ["5m", "15m"]
    assert summary["representative_id"] == 1


def test_confluence_is_immutable() -> None:
    rows = [_row(timeframe="5m"), _row(timeframe="15m", row_id=2)]
    confluence = detect_from_rows(rows, symbol="XAUUSD", action="BUY", timeframe="15m")
    assert confluence is not None
    assert isinstance(confluence, Confluence)

    with pytest.raises(dataclasses.FrozenInstanceError):
        confluence.confidence = 0.99  # type: ignore[misc]
