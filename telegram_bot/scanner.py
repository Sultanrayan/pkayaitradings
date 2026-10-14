"""The scanner: what runs on a schedule, and what it is allowed to send.

One pass covers every enabled ``(symbol, timeframe)`` pair. For each pair it
computes the signal, checks the per-pair cooldown and hourly cap, looks for
confluence, stores the result, and returns what should be delivered. The caller
decides whether to send — this module never touches Telegram, which is what makes
it testable without a network.

Delivery rules, in the order they are applied:

1. **Already stored?** Skip. The ``UNIQUE`` constraint makes this idempotent, so a
   restart mid-pass cannot re-announce the same bar.
2. **Quiet hour?** Compute and store, but do not deliver. Suppressing delivery
   while keeping the record means the performance history stays complete.
3. **Cooldown?** Compute and store, do not deliver.
4. **Hourly cap?** Compute and store, do not deliver.
5. **No signal?** Nothing to store.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from shared.logging import get_logger
from telegram_bot.confluence import Confluence, detect_confluence
from telegram_bot.db import Database, utcnow
from telegram_bot.defaults import BotConfig
from telegram_bot.engine import (
    Signal,
    bar_close_seconds,
    compute_signal,
    update_signal_outcome,
)
from telegram_bot.market import BarsUnavailableError, DataError, MarketData

_logger = get_logger(__name__)

__all__ = ["ScanResult", "Scanner", "SuppressionReason"]

#: Why a computed signal was not delivered.
SuppressionReason = str


@dataclass
class ScanResult:
    """What one pass decided, per pair.

    Attributes:
        computed: Signals computed, whether or not delivered.
        delivered: Signals that should be sent now.
        stored: Signals written to the database.
        confluences: Confluences detected.
        suppressed: Pair -> reason, for signals computed but withheld.
        gated: Pair -> reason, for signals stored but withheld by the broadcast
            gate. Distinct from `suppressed` because the gate judges the quality
            of the signal rather than its timing or safety.
        errors: Pair -> error text.
        order_flow: Latest order-flow snapshot per symbol.
    """

    computed: list[Signal] = field(default_factory=list)
    delivered: list[Signal] = field(default_factory=list)
    stored: list[Signal] = field(default_factory=list)
    confluences: list[Confluence] = field(default_factory=list)
    suppressed: dict[str, str] = field(default_factory=dict)
    gated: dict[str, str] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)
    order_flow: dict[str, Any] = field(default_factory=dict)

    @property
    def has_deliveries(self) -> bool:
        """Whether anything should be sent."""
        return bool(self.delivered)

    def summary(self) -> dict[str, Any]:
        """Counts for a structured log line."""
        return {
            "computed": len(self.computed),
            "delivered": len(self.delivered),
            "stored": len(self.stored),
            "confluences": len(self.confluences),
            "suppressed": len(self.suppressed),
            "errors": len(self.errors),
        }


class Scanner:
    """Runs the signal pass over every enabled pair.

    Args:
        db: Database.
        config: Bot configuration.
        market: Data source. Owned by the caller.
        started_at: Process start time, used for uptime.
    """

    def __init__(
        self,
        *,
        db: Database,
        config: BotConfig,
        market: MarketData,
        started_at: float | None = None,
    ) -> None:
        self.db = db
        self.config = config
        self.market = market
        self.started_at = started_at if started_at is not None else time.time()

    @property
    def uptime_seconds(self) -> int:
        """Seconds since the scanner was constructed."""
        return max(0, int(time.time() - self.started_at))

    async def scan(
        self,
        *,
        symbol: str | None = None,
        timeframe: str | None = None,
        now: int | None = None,
        respect_delivery_rules: bool = True,
    ) -> ScanResult:
        """Run one pass.

        Args:
            symbol: Restrict to one symbol, or ``None`` for all.
            timeframe: Restrict to one timeframe, or ``None`` for all.
            now: Injected clock. ``None`` means "now".
            respect_delivery_rules: Set ``False`` for a manual ``/agenza`` reply,
                which must answer the user even when the auto-alert path would
                have suppressed the message.

        Returns:
            A :class:`ScanResult`. Never raises for a per-pair failure — one bad
            symbol must not abandon the rest of the pass.
        """
        result = ScanResult()
        now_ts = now if now is not None else utcnow()

        pairs = self._pairs(symbol, timeframe)
        _logger.info("scan.start", pairs=len(pairs), now=now_ts)

        for sym, tf in pairs:
            key = f"{sym}:{tf}"
            try:
                frame = await self.market.closed_frame(sym, tf)
            except BarsUnavailableError as exc:
                result.errors[key] = str(exc)
                _logger.info("scan.no_bars", symbol=sym, timeframe=tf)
                continue
            except DataError as exc:
                result.errors[key] = str(exc)
                _logger.warning("scan.fetch_failed", symbol=sym, timeframe=tf, error=str(exc))
                continue

            signal = compute_signal(
                frame, symbol=sym, timeframe=tf, config=self.config, now=now_ts
            )
            if signal is None:
                continue

            result.computed.append(signal)
            self._resolve_outcomes(signal, frame)

            if self.db.has_signal(sym, tf, signal.bar_ts, signal.action):
                # Already recorded, so nothing to store and nothing to announce.
                continue

            # Suppression is decided BEFORE the row is written. Both checks read
            # the pair's history — the last signal time and the last hour's count
            # — so recording first would make a pair's very first signal suppress
            # itself on its own cooldown and never be sent.
            reason = self._suppression_reason(sym, tf, now_ts) if respect_delivery_rules else None

            self._record(signal, now=now_ts)
            result.stored.append(signal)

            if reason:
                result.suppressed[key] = reason
                _logger.info("scan.suppressed", symbol=sym, timeframe=tf, reason=reason)
                continue

            # --- Broadcast gate ---
            #
            # Applied after recording and after cooldown, so a gated signal is
            # still stored, still counted and still suppresses its own pair for
            # the cooldown window. Only the outbound message is withheld.
            if not self.config.passes_broadcast_gate(signal.strength, signal.confidence):
                result.gated[key] = (
                    f"below broadcast gate (strength={signal.strength or 'unset'}, "
                    f"confidence={signal.confidence:.2f})"
                )
                _logger.info(
                    "scan.gated",
                    symbol=sym,
                    timeframe=tf,
                    strength=signal.strength,
                    confidence=signal.confidence,
                )
                continue

            result.delivered.append(signal)

            confluence = detect_confluence(
                self.db,
                symbol=sym,
                timeframe=tf,
                action=signal.action,
                config=self.config,
                now_ts=now_ts,
            )
            if confluence is not None:
                result.confluences.append(confluence)

        result.order_flow = await self.collect_order_flow(pairs)
        _logger.info("scan.complete", **result.summary())
        return result

    def _pairs(self, symbol: str | None, timeframe: str | None) -> list[tuple[str, str]]:
        """Pairs to scan, honouring any filter."""
        pairs = self.db.all_pairs()
        if symbol is not None:
            upper = symbol.upper()
            pairs = [p for p in pairs if p[0] == upper]
        if timeframe is not None:
            pairs = [p for p in pairs if p[1] == timeframe]
        return pairs

    def _suppression_reason(self, symbol: str, timeframe: str, now_ts: int) -> str | None:
        """Why this pair must not deliver right now, or ``None`` to deliver.

        Must be called before the signal being considered is written, because both
        the cooldown and the hourly cap are measured against what the pair has
        already sent. Deciding after recording makes a pair's first signal
        suppress itself.
        """
        if self.config.is_quiet_hour(_utc_hour(now_ts)):
            return "quiet_hour"

        settings = self.db.timeframe_settings(symbol, timeframe)
        cooldown = int(settings["cooldown_minutes"])
        last = self.db.last_signal_time(symbol, timeframe)
        if last is not None and cooldown > 0:
            elapsed_minutes = (now_ts - int(last)) / 60.0
            if elapsed_minutes < cooldown:
                return f"cooldown_{int(cooldown - elapsed_minutes)}m"

        cap = int(settings["max_signals_per_hour"] or 0)
        if cap > 0:
            recent = self.db.count_signals_for_pair_since(symbol, timeframe, now_ts - 3_600)
            if recent >= cap:
                return "hourly_cap"

        return None

    def _record(self, signal: Signal, *, now: int) -> None:
        """Write a signal to the database, ignoring a duplicate."""
        try:
            row_id = self.db.save_signal(signal.to_record(sent_at=now))
        except Exception as exc:
            _logger.exception(
                "scan.record_failed", symbol=signal.symbol, timeframe=signal.timeframe
            )
            _logger.error("scan.record_error", error=repr(exc))
            return
        if row_id is None:
            _logger.info(
                "scan.duplicate_ignored",
                symbol=signal.symbol,
                timeframe=signal.timeframe,
                bar_ts=signal.bar_ts,
            )

    def _resolve_outcomes(self, signal: Signal, frame: pd.DataFrame) -> None:
        """Close open signals of this pair whose target or stop this bar reached.

        Only bars *after* the signal's own bar are considered. Including the
        signal bar would let a bar that produced the signal immediately resolve it.
        """
        rows = [
            row
            for row in self.db.open_signals()
            if row.symbol == signal.symbol and row.timeframe == signal.timeframe
        ]
        for row in rows:
            after = frame[bar_close_seconds(frame.index) > row.timestamp]
            if after.empty:
                continue
            last = after.iloc[-1]
            outcome = update_signal_outcome(
                signal, high=float(last["high"]), low=float(last["low"])
            )
            if outcome is None:
                continue
            exit_price = row.tp1 if outcome == "win" else row.sl
            move = (exit_price - row.entry) / row.entry * 100.0
            pnl = move if row.action == "BUY" else -move
            self.db.set_outcome(row.id, outcome, pnl)
            _logger.info(
                "scan.outcome",
                signal_id=row.id,
                symbol=row.symbol,
                timeframe=row.timeframe,
                outcome=outcome,
                pnl_pct=round(pnl, 3),
            )

    async def collect_order_flow(self, pairs: list[tuple[str, str]]) -> dict[str, Any]:
        """Latest order-flow snapshot per symbol, from the cached frames.

        Reads the cache rather than fetching: ``/orderflow`` must be fast, and a
        fetch per symbol per call would make the command the slowest thing in the
        bot.
        """
        from telegram_bot.orderflow import compute_order_flow

        snapshots: dict[str, Any] = {}
        for symbol, timeframe in pairs:
            if symbol in snapshots:
                continue
            frame = self.market.cached_frame(symbol, timeframe)
            if frame is None or frame.empty:
                continue
            try:
                snapshots[symbol] = compute_order_flow(
                    frame, symbol=symbol, timeframe=timeframe, position=-1
                ).to_dict()
            except Exception as exc:
                _logger.warning("scan.order_flow_failed", symbol=symbol, error=repr(exc))
        return snapshots


def _utc_hour(ts: int) -> int:
    """UTC hour for a Unix timestamp."""
    from datetime import UTC, datetime

    return datetime.fromtimestamp(int(ts), tz=UTC).hour
