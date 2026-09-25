"""In-memory OHLC accumulation store.

biquote only retains a shallow intraday history window (verified against the
live API: roughly 5h of M1, 1 day of M5, 7 days of H1), so a single fetch can
never fill a chart for short timeframes. Worse, every refetch returns a
*sliding* window - new bars appear on the right while old bars fall off the
left - which makes the chart look like it "moves" even before fresh data
arrives.

This store merges every fetched series keyed by ``(symbol, interval)`` so the
backend accumulates a stable, growing candle history over time instead of
serving biquote's ever-shifting window.
"""

from __future__ import annotations

from datetime import datetime

from shared.schemas.market import OhlcBar

_DEFAULT_MAX_BARS = 2_000


class OhlcStore:
    """Accumulate OHLC bars per (symbol, interval).

    Bars are keyed by their ``open_time`` so updates to the in-progress bar
    replace in place. The store only ever grows; it is capped per series to
    bound memory usage.
    """

    def __init__(self, *, max_bars_per_series: int = _DEFAULT_MAX_BARS) -> None:
        self._max_bars = max_bars_per_series
        self._series: dict[tuple[str, str], dict[datetime, OhlcBar]] = {}

    def _bucket(self, symbol: str, interval: str) -> dict[datetime, OhlcBar]:
        key = (symbol.upper(), interval)
        bucket = self._series.get(key)
        if bucket is None:
            bucket = self._series[key] = {}
        return bucket

    def _upsert(self, bucket: dict[datetime, OhlcBar], bars: list[OhlcBar]) -> None:
        for bar in bars:
            bucket[bar.open_time] = bar
        if len(bucket) > self._max_bars:
            oldest = sorted(bucket)[: len(bucket) - self._max_bars]
            for timestamp in oldest:
                del bucket[timestamp]

    @staticmethod
    def _ordered(bucket: dict[datetime, OhlcBar]) -> list[OhlcBar]:
        return [bucket[timestamp] for timestamp in sorted(bucket)]

    def merge(
        self, symbol: str, interval: str, bars: list[OhlcBar], *, limit: int | None = None
    ) -> list[OhlcBar]:
        """Merge fetched bars and return the most recent ``limit`` oldests-first.

        When ``limit`` is ``None`` (or non-positive) the full merged series is
        returned.
        """
        bucket = self._bucket(symbol, interval)
        self._upsert(bucket, bars)
        ordered = self._ordered(bucket)
        if limit and limit > 0 and len(ordered) > limit:
            return ordered[-limit:]
        return ordered

    def upsert(self, symbol: str, interval: str, bars: list[OhlcBar]) -> None:
        """Persist bars without trimming the returned series."""
        bucket = self._bucket(symbol, interval)
        self._upsert(bucket, bars)

    def __len__(self) -> int:
        return sum(len(bucket) for bucket in self._series.values())
