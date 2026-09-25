"""Tests for the in-memory OHLC accumulation store."""

from __future__ import annotations

from datetime import UTC, datetime

from data_pipeline.ohlc_store import OhlcStore
from shared.schemas.market import OhlcBar


def _bar(open_time: str, **overrides: object) -> OhlcBar:
    data: dict[str, object] = {
        "openTime": open_time,
        "open": 1.0,
        "high": 2.0,
        "low": 0.5,
        "close": 1.5,
        "volume": 0,
        "tickVolume": 10,
        "isOpen": False,
    }
    data.update(overrides)
    return OhlcBar.model_validate(data)


def test_merge_returns_oldest_first() -> None:
    store = OhlcStore()
    bars = store.merge("XAUUSD", "1m", [_bar("2026-01-01T00:02:00Z"), _bar("2026-01-01T00:01:00Z")])
    assert [bar.open_time for bar in bars] == [
        datetime(2026, 1, 1, 0, 1, tzinfo=UTC),
        datetime(2026, 1, 1, 0, 2, tzinfo=UTC),
    ]


def test_merge_accumulates_across_calls() -> None:
    store = OhlcStore()
    first = store.merge("XAUUSD", "1m", [_bar("2026-01-01T00:02:00Z"), _bar("2026-01-01T00:01:00Z")])
    second = store.merge("XAUUSD", "1m", [_bar("2026-01-01T00:04:00Z"), _bar("2026-01-01T00:03:00Z")])
    assert len(first) == 2
    assert len(second) == 4
    assert [bar.close for bar in second] == [1.5, 1.5, 1.5, 1.5]


def test_merge_replaces_in_progress_bar() -> None:
    store = OhlcStore()
    store.merge("XAUUSD", "1m", [_bar("2026-01-01T00:01:00Z", close=1.5, isOpen=True)])
    updated = store.merge("XAUUSD", "1m", [_bar("2026-01-01T00:01:00Z", close=2.5, isOpen=True)])
    assert [bar.close for bar in updated] == [2.5]


def test_merge_limit_trims_to_most_recent() -> None:
    store = OhlcStore()
    store.merge("XAUUSD", "1m", [_bar(f"2026-01-01T00:{i:02d}:00Z") for i in range(1, 11)])
    trimmed = store.merge("XAUUSD", "1m", [], limit=3)
    assert [bar.open_time.minute for bar in trimmed] == [8, 9, 10]


def test_series_are_isolated_per_symbol_interval() -> None:
    store = OhlcStore()
    store.merge("XAUUSD", "1m", [_bar("2026-01-01T00:01:00Z")])
    store.merge("XAUUSD", "1h", [_bar("2026-01-01T00:00:00Z")])
    store.merge("BTCUSD", "1m", [_bar("2026-01-01T00:01:00Z")])
    assert len(store) == 3


def test_cap_bounds_memory() -> None:
    store = OhlcStore(max_bars_per_series=5)
    store.merge("XAUUSD", "1m", [_bar(f"2026-01-01T00:{i:02d}:00Z") for i in range(1, 12)])
    assert len(store) == 5
    assert [bar.open_time.minute for bar in store.merge("XAUUSD", "1m", [])] == [7, 8, 9, 10, 11]


def test_upsert_persists_without_trimming() -> None:
    store = OhlcStore()
    store.upsert("XAUUSD", "1m", [_bar("2026-01-01T00:01:00Z")])
    assert len(store) == 1
    # upsert does not return the series; a later merge exposes the persisted bars
    persisted = store.merge("XAUUSD", "1m", [], limit=None)
    assert [bar.open_time for bar in persisted] == [datetime(2026, 1, 1, 0, 1, tzinfo=UTC)]


def test_limit_zero_or_none_returns_full_series() -> None:
    store = OhlcStore()
    store.merge("XAUUSD", "1m", [_bar("2026-01-01T00:01:00Z")])
    assert len(store.merge("XAUUSD", "1m", [], limit=None)) == 1
    assert len(store.merge("XAUUSD", "1m", [], limit=0)) == 1
