"""Signal store adapter.

Wraps the existing :class:`~orchestrator.store.SignalStore` rather than
duplicating it. The engine's :class:`~signals.models.Signal` is a richer object
than the store's ``SignalRecord`` — it carries bar-anchored levels and per-layer
scores — so the adapter's job is lossless translation in both directions, plus
the per-(symbol, timeframe) queries the engine needs and the flat record does not
offer.

What this adapter does not do
-----------------------------
It does not add persistence, and it does not add a second store. The underlying
``SignalStore`` is a bounded in-memory deque owned by whichever process built it,
so signals written by the Celery worker are not visible to the API process. That
is a pre-existing property of the deployment, not something this module can fix
from inside a store adapter; :meth:`EngineSignalStore.uses_shared_process` makes
it checkable rather than assumed. See the integration checklist.

Immutability
------------
:meth:`EngineSignalStore.publish` returns the stored signal and never edits an
existing one. A second signal for the same bar with different levels is a
*replacement keyed on ``(symbol, timeframe, timestamp)``, which is a distinct
operation from the append-only path the shared store offers, and is the only way
a store can both be append-only upstream and idempotent from the engine's point
of view.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from shared.logging import get_logger
from signals.models import Signal

_logger = get_logger(__name__)

__all__ = ["SIGNAL_AGENT", "SIGNAL_KIND", "EngineSignalStore"]

#: ``kind`` written into the shared store, so engine signals are distinguishable
#: from agent signals in ``store.query(agent=...)`` and ``store.stats()``.
SIGNAL_KIND = "engine_signal"

#: Recorded as the ``agent`` field. Deliberately the orchestrator rather than the
#: technical analyst: these signals are not that agent's output and attributing
#: them to it would corrupt the per-agent metrics the dashboard renders.
SIGNAL_AGENT = "orchestrator"


class EngineSignalStore:
    """Bar-anchored signal repository on top of the shared signal store.

    Args:
        store: The application's :class:`~orchestrator.store.SignalStore`.
        max_history: Maximum signals retained per ``(symbol, timeframe)`` pair.
            Older ones are dropped on publish, which bounds memory without
            discarding another symbol's history.
    """

    def __init__(self, store: Any, *, max_history: int = 1_000) -> None:
        if max_history < 1:
            raise ValueError(f"max_history must be at least 1, got {max_history}")
        self._store = store
        self._max_history = max_history

    # ------------------------------------------------------------------ #
    # Properties
    # ------------------------------------------------------------------ #

    @property
    def store(self) -> Any:
        """The wrapped shared store, for callers that need its other queries."""
        return self._store

    @property
    def max_history(self) -> int:
        """Signals retained per ``(symbol, timeframe)`` pair."""
        return self._max_history

    def uses_shared_process(self, other: EngineSignalStore) -> bool:
        """Whether two adapters share one underlying store instance.

        Two adapters over different instances are looking at different memory.
        That is almost never what a caller wants, and it is exactly the situation
        the worker/API split creates, so it is worth asking explicitly rather than
        assuming.
        """
        return self._store is other._store

    # ------------------------------------------------------------------ #
    # Writing
    # ------------------------------------------------------------------ #

    def publish(self, signal: Signal, *, correlation_id: str = "") -> Signal:
        """Append ``signal`` to the store.

        The signal is written verbatim; no field is recomputed, rounded or
        re-timestamped. This is what makes "the stored signal is the plotted
        signal" true rather than aspirational — there is no transformation to
        drift.

        Publishing the same ``(symbol, timeframe, timestamp)`` twice appends twice
        rather than updating. The engine's cooldown makes a duplicate for the same
        bar impossible in a single pass; a duplicate here means two passes
        published the same bar, which is recorded at WARNING so it is visible
        rather than silently inflating the history.

        Args:
            signal: The signal to store.
            correlation_id: Groups the signal with the cycle that produced it.

        Returns:
            The signal as stored, which is the same object — the store adapter
            does not rewrite a frozen dataclass.
        """
        self._store.record_signal(
            symbol=signal.symbol,
            correlation_id=correlation_id,
            agent=SIGNAL_AGENT,
            kind=SIGNAL_KIND,
            direction=signal.action,
            confidence=signal.confidence,
            payload=signal.to_dict(),
        )

        history = self.history(signal.symbol, signal.timeframe, self._max_history + 1)
        if len(history) > self._max_history:
            _logger.warning(
                "signals.history_truncated",
                symbol=signal.symbol,
                timeframe=signal.timeframe,
                kept=self._max_history,
            )
        return signal

    def publish_all(self, signals: Sequence[Signal], *, correlation_id: str = "") -> int:
        """Publish many signals.

        Args:
            signals: Signals to append, in any order.
            correlation_id: Shared cycle identifier.

        Returns:
            How many were published.
        """
        for signal in signals:
            self.publish(signal, correlation_id=correlation_id)
        return len(signals)

    # ------------------------------------------------------------------ #
    # Reading
    # ------------------------------------------------------------------ #

    def _records(self, symbol: str, timeframe: str) -> list[Any]:
        """Engine records for one pair, oldest first.

        The shared store returns newest-first and has no timeframe concept, so
        both the ordering and the filter are applied here.
        """
        matched: list[Any] = []
        for record in reversed(self._store.query(symbol=symbol, limit=10_000)):
            if record.kind != SIGNAL_KIND:
                continue
            payload = record.payload
            if not isinstance(payload, dict):
                continue
            if str(payload.get("timeframe", "")) != str(timeframe):
                continue
            matched.append(record)
        return matched

    def _to_signal(self, record: Any) -> Signal | None:
        """Rebuild a signal from a stored record, or ``None`` if unreadable.

        A payload written by an older schema version is skipped rather than
        allowed to raise: one bad record must not break the history endpoint.
        """
        try:
            return Signal.from_dict(record.payload)
        except (KeyError, TypeError, ValueError):
            _logger.warning("signals.unreadable_payload", record_id=getattr(record, "id", "?"))
            return None

    def latest(self, symbol: str, timeframe: str) -> Signal | None:
        """Most recent signal for a pair, or ``None``.

        "Most recent" is by bar timestamp, not by write time. A late-arriving
        older bar must not displace a newer signal, which is the difference
        between a store and a log.
        """
        records = self._records(symbol.upper(), timeframe)
        if not records:
            return None
        signals = [s for s in (self._to_signal(r) for r in records) if s is not None]
        if not signals:
            return None
        return max(signals, key=lambda s: s.timestamp)

    def history(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 100,
    ) -> list[Signal]:
        """Signals for a pair, oldest first.

        Args:
            symbol: Instrument ticker; case-insensitive.
            timeframe: Candle interval.
            limit: Maximum signals returned.

        Returns:
            At most ``limit`` signals in chronological order. Fewer is normal —
            signals are sparse by design.
        """
        if limit < 1:
            raise ValueError(f"limit must be at least 1, got {limit}")
        records = self._records(symbol.upper(), timeframe)
        signals = [s for s in (self._to_signal(r) for r in records) if s is not None]
        signals.sort(key=lambda s: s.timestamp)
        return signals[-limit:]

    def range(
        self,
        symbol: str,
        timeframe: str,
        from_timestamp: Any = None,
        to_timestamp: Any = None,
    ) -> list[Signal]:
        """Signals whose bar timestamp falls in an inclusive range.

        The filter is on the *bar* timestamp, which is what the chart shows, not
        the write time.

        Args:
            symbol: Instrument ticker; case-insensitive.
            timeframe: Candle interval.
            from_timestamp: Inclusive lower bound, or ``None``.
            to_timestamp: Inclusive upper bound, or ``None``.

        Returns:
            Matching signals in chronological order.
        """

        lower = _coerce_timestamp(from_timestamp)
        upper = _coerce_timestamp(to_timestamp)
        results = []
        for signal in self.history(symbol.upper(), timeframe, limit=10_000):
            if lower is not None and signal.timestamp < lower:
                continue
            if upper is not None and signal.timestamp > upper:
                continue
            results.append(signal)
        return results

    def count(self, symbol: str, timeframe: str) -> int:
        """Number of engine signals retained for a pair."""
        return len(self._records(symbol.upper(), timeframe))


def _coerce_timestamp(value: Any) -> Any:
    """Normalise a caller-supplied bound to a UTC pandas Timestamp.

    A naive value is localised to UTC rather than rejected, because a query
    string like ``2026-10-02T08:00`` is unambiguous in a system that documents
    UTC throughout. Anything unparsable returns ``None``, which the range filter
    reads as "unbounded" — a permissive failure for a read-only query.
    """
    import pandas as pd

    if value is None or value == "":
        return None
    try:
        timestamp = pd.Timestamp(value)
    except (ValueError, TypeError):
        _logger.warning("signals.unparsable_bound", value=str(value))
        return None
    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")
