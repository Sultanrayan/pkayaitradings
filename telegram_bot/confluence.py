"""Multi-timeframe confluence.

A confluence is two or more timeframes of the **same symbol** agreeing on
direction within a short window. Cross-symbol confluence is explicitly not
supported: gold buying out while bitcoin sells is two facts, not one stronger
fact, and merging them would let an unrelated instrument manufacture confidence.

Window semantics
----------------
A higher timeframe may only count once its bar has **closed**. Counting a 1h
signal against a 5m signal while the hour bar is still forming would let a signal
appear and then change as the hour completed — the repaint this whole bot is built
to avoid.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from telegram_bot.db import Database, SignalRow
from telegram_bot.timeframes import bar_seconds

__all__ = ["Confluence", "detect_confluence", "detect_from_rows"]


@dataclass(frozen=True)
class Confluence:
    """Agreement across at least two timeframes of one symbol.

    Attributes:
        symbol: Instrument ticker.
        action: Shared direction, ``BUY`` or ``SELL``.
        timeframes: Participating timeframes, ascending.
        confidence: Confidence weighted by how many timeframes agree.
        representative: The signal whose levels are published — the shortest
            timeframe in the group, which has the tightest levels and the fastest
            confirmation.
        members: Every participating signal.
    """

    symbol: str
    action: str
    timeframes: tuple[str, ...]
    confidence: float
    representative: SignalRow
    members: tuple[SignalRow, ...]

    def to_dict(self) -> dict[str, Any]:
        """JSON-ready summary for storage."""
        return {
            "symbol": self.symbol,
            "action": self.action,
            "timeframes": list(self.timeframes),
            "confidence": self.confidence,
            "representative_id": self.representative.id,
        }


def detect_confluence(
    db: Database,
    *,
    symbol: str,
    timeframe: str,
    action: str,
    config: Any,
    now_ts: int,
) -> Confluence | None:
    """Look for agreement between ``timeframe`` and the other timeframes.

    Args:
        db: Database holding recent signals.
        symbol: Instrument ticker. Confluence never crosses symbols.
        timeframe: The timeframe of the signal just fired.
        action: That signal's direction.
        config: Supplies ``confluence_min_tfs`` and ``confluence_window_candles``.
        now_ts: Current Unix seconds, used to bound the window.

    Returns:
        A :class:`Confluence` when at least ``confluence_min_tfs`` timeframes
        agree, otherwise ``None``.
    """
    if not getattr(config, "confluence_enabled", True):
        return None

    min_tfs = max(2, int(getattr(config, "confluence_min_tfs", 2)))
    window_candles = max(1, int(getattr(config, "confluence_window_candles", 3)))
    window_seconds = bar_seconds(timeframe) * window_candles
    start_ts = int(now_ts) - window_seconds

    # Only timeframes at or below the triggering one can have closed. A 1h signal
    # may not be confluent with 5m because 5m is finer and has not "closed" in the
    # sense of completing after the hour.
    eligible = [tf for tf in _all_timeframes() if bar_seconds(tf) <= bar_seconds(timeframe)]
    rows: list[SignalRow] = []
    for tf in eligible:
        found = db.signals_in_window(symbol, tf, start_ts, int(now_ts))
        rows.extend(row for row in found if row.action == action)

    return detect_from_rows(
        rows,
        symbol=symbol,
        action=action,
        timeframe=timeframe,
        min_tfs=min_tfs,
    )


def detect_from_rows(
    rows: Sequence[SignalRow],
    *,
    symbol: str,
    action: str,
    timeframe: str,
    min_tfs: int = 2,
) -> Confluence | None:
    """Build a confluence from already-fetched rows.

    Split out from :func:`detect_confluence` so the agreement logic is testable
    without a database, and so the window arithmetic is separated from the
    counting.

    Args:
        rows: Candidate signals, already filtered to one symbol, one action and a
            closed window.
        symbol: Instrument ticker.
        action: Shared direction.
        timeframe: The triggering timeframe.
        min_tfs: Minimum agreeing timeframes required. Values below 2 are raised
            to 2, since one timeframe cannot agree with itself.

    Returns:
        A :class:`Confluence`, or ``None`` when too few agree.
    """
    # Clamped here as well as in the caller. `detect_from_rows` is part of the
    # public surface, and a config of 1 would otherwise let a single timeframe
    # declare a confluence with itself — which is the one thing the word excludes.
    min_tfs = max(2, min_tfs)

    matching = [
        row
        for row in rows
        if row.symbol.upper() == symbol.upper() and row.action == action
    ]
    if not matching:
        return None

    # One signal per timeframe: the newest within the window.
    by_timeframe: dict[str, SignalRow] = {}
    for row in matching:
        current = by_timeframe.get(row.timeframe)
        if current is None or row.timestamp > current.timestamp:
            by_timeframe[row.timeframe] = row

    if len(by_timeframe) < min_tfs:
        return None

    members = tuple(
        sorted(by_timeframe.values(), key=lambda r: bar_seconds(r.timeframe))
    )
    timeframes = tuple(row.timeframe for row in members)

    # Weight by timeframe: a 1h agreement counts for more than a 1m one.
    total_weight = sum(bar_seconds(tf) for tf in timeframes)
    confidence = (
        sum(row.confidence * bar_seconds(row.timeframe) for row in members)
        / total_weight
        if total_weight > 0
        else 0.0
    )
    # Three or more agreeing timeframes is worth a small premium, capped so it can
    # never manufacture confidence out of a thin margin.
    bonus = min(0.10, 0.03 * (len(timeframes) - 2))
    confidence = min(1.0, confidence + bonus)

    # Publish the finest timeframe's levels: tightest stop, fastest confirmation.
    representative = members[0]
    return Confluence(
        symbol=symbol.upper(),
        action=action,
        timeframes=timeframes,
        confidence=confidence,
        representative=representative,
        members=members,
    )


def _all_timeframes() -> tuple[str, ...]:
    """Every internal timeframe the bot knows, coarsest first."""
    from telegram_bot.defaults import DEFAULT_TIMEFRAMES

    return tuple(sorted(DEFAULT_TIMEFRAMES, key=bar_seconds, reverse=True))


def confluence_label(timeframes: Sequence[str]) -> str:
    """Render participating timeframes for display, e.g. ``5mn + 15mn + 1h``."""
    from telegram_bot.timeframes import INTERNAL_TO_USER

    return " + ".join(INTERNAL_TO_USER.get(tf, tf) for tf in timeframes)
