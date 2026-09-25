"""Tests for the vector store, database models and tick feed."""

from __future__ import annotations

import asyncio

from shared.database.base import Base, create_engine, create_session_factory
from shared.database.models import OhlcvRecord, TickRecord
from shared.database.repository import store_ticks
from shared.schemas.enums import MarketState, Timeframe
from shared.schemas.market import OhlcSeries, Tick
from shared.utils.time import utcnow
from shared.vector_store import HashingEmbedder, InMemoryVectorStore, build_vector_store


def _tick(symbol: str = "XAUUSD", mid: float = 2650.0) -> Tick:
    return Tick(
        symbol=symbol,
        bid=mid - 0.2,
        ask=mid + 0.2,
        mid=mid,
        spread=0.4,
        timestamp=utcnow(),
        marketState=MarketState.OPEN.value,
    )


async def test_hashing_embedder_is_normalised() -> None:
    embedder = HashingEmbedder(dimension=64)
    vectors = await embedder.embed(["gold rallies on dovish fed"])
    assert len(vectors) == 1
    norm = sum(value * value for value in vectors[0]) ** 0.5
    assert norm == 1.0 or norm == 0.0


async def test_in_memory_vector_store_ranks_by_similarity() -> None:
    embedder = HashingEmbedder(dimension=128)
    store = InMemoryVectorStore()
    texts = ["gold rallies on dovish fed", "bitcoin plunges after hack", "gold safe haven demand"]
    vectors = await embedder.embed(texts)
    await store.upsert(
        ids=["a", "b", "c"], vectors=vectors, payloads=[{"i": 0}, {"i": 1}, {"i": 2}]
    )
    query = (await embedder.embed(["gold rallies"]))[0]
    results = await store.search(query, limit=2)
    assert results
    assert results[0].id in {"a", "c"}


def test_build_vector_store_falls_back_to_memory() -> None:
    store, embedder = build_vector_store()
    assert isinstance(store, InMemoryVectorStore)
    assert isinstance(embedder, HashingEmbedder)


def test_models_register_tables() -> None:
    tables = Base.metadata.tables
    assert "ticks" in tables
    assert "ohlcv" in tables
    assert TickRecord.__tablename__ == "ticks"
    assert OhlcvRecord.__tablename__ == "ohlcv"


def test_create_engine_and_session_factory() -> None:
    engine = create_engine()
    factory = create_session_factory(engine)
    assert factory is not None


async def test_store_ticks_empty_is_noop() -> None:
    assert await store_ticks(None, []) == 0  # type: ignore[arg-type]


async def test_polling_feed_emits_snapshot_ticks() -> None:
    from data_pipeline.biquote_feed import PollingTickFeed

    class _Client:
        async def get_latest(self, symbols: list[str], **_: object) -> dict[str, Tick]:
            return {symbol: _tick(symbol) for symbol in symbols}

        async def close(self) -> None:
            return None

    feed = PollingTickFeed(["XAUUSD"], interval_seconds=0.05, client=_Client())  # type: ignore[arg-type]
    await feed.start()
    try:
        stream = feed.stream()
        tick = await asyncio.wait_for(anext(stream), timeout=2.0)
        assert tick.symbol == "XAUUSD"
    finally:
        await feed.stop()


def test_biquote_feed_drops_malformed_ticks() -> None:
    from data_pipeline.biquote_feed import BiquoteTickFeed

    feed = BiquoteTickFeed(["XAUUSD"])
    feed._on_tick([{"symbol": "XAUUSD"}])  # malformed: missing prices
    feed._on_tick([_tick().model_dump(mode="json")])
    assert feed._queue.qsize() == 1


def test_ohlc_series_helpers() -> None:
    from shared.schemas.market import OhlcBar

    series = OhlcSeries(
        symbol="XAUUSD",
        interval="1h",
        bars=(
            OhlcBar(openTime=utcnow(), open=1, high=2, low=0.5, close=1.5, isOpen=False),
            OhlcBar(openTime=utcnow(), open=1.5, high=2.5, low=1, close=2, isOpen=True),
        ),
    )
    assert len(series.closed_bars) == 1
    assert series.latest_close == 2
    assert Timeframe.H1.biquote_interval == "1h"
