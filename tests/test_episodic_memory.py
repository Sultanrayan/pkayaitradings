"""Tests for the episodic memory (record + recall with win-rate scoring)."""

from __future__ import annotations

import pytest

from shared.episodic_memory import (
    Episode,
    EpisodicMemory,
    FeatureVectorizer,
    MemoryRecall,
)
from shared.vector_store.store import InMemoryVectorStore, SearchResult


def make_features(direction: float = 1.0, confidence: float = 0.8) -> dict[str, float]:
    return {
        "direction": direction,
        "confidence": confidence,
        "rsi": 0.7,
        "adx": 0.5,
        "news_sentiment": 0.75,
        "risk_approved": 1.0,
        "regime": 1.0,
    }


async def test_recall_needs_min_samples() -> None:
    memory = EpisodicMemory(store=InMemoryVectorStore())
    await memory.record(
        Episode(correlation_id="a", symbol="XAUUSD", features=make_features(), decision="BUY", outcome=1.0)
    )
    recall = await memory.recall(make_features())
    assert recall.samples == 1
    assert recall.win_rate is None
    assert recall.adjustment == 0.0


async def test_recall_computes_win_rate_and_adjustment() -> None:
    memory = EpisodicMemory(store=InMemoryVectorStore(), settings=None)
    features = make_features()
    for index, outcome in enumerate([1.0, 1.0, 1.0, 0.0, 1.0]):
        await memory.record(
            Episode(
                correlation_id=f"id-{index}",
                symbol="XAUUSD",
                features=features,
                decision="BUY",
                outcome=outcome,
            )
        )
    recall = await memory.recall(features)
    assert recall.samples == 5
    assert recall.win_rate == pytest.approx(0.8)
    assert recall.adjustment > 0.0


async def test_poor_win_rate_gives_negative_adjustment() -> None:
    memory = EpisodicMemory(store=InMemoryVectorStore())
    features = make_features()
    for index in range(8):
        await memory.record(
            Episode(
                correlation_id=f"lose-{index}",
                symbol="XAUUSD",
                features=features,
                decision="BUY",
                outcome=0.0,
            )
        )
    recall = await memory.recall(features)
    assert recall.win_rate == pytest.approx(0.0)
    assert recall.adjustment < 0.0


async def test_recall_ignores_unresolved_episodes() -> None:
    memory = EpisodicMemory(store=InMemoryVectorStore())
    await memory.record(
        Episode(correlation_id="open", symbol="XAUUSD", features=make_features(), decision="BUY")
    )
    recall = await memory.recall(make_features())
    assert recall.samples == 0
    assert recall.win_rate is None
    assert recall.adjustment == 0.0


async def test_recall_is_defensive_on_store_error() -> None:
    class _BrokenStore(InMemoryVectorStore):
        async def search(
            self, vector: list[float], *, limit: int = 5
        ) -> list[SearchResult]:
            raise RuntimeError("store down")

    memory = EpisodicMemory(store=_BrokenStore())
    recall = await memory.recall(make_features())
    assert recall == MemoryRecall(samples=0, win_rate=None, adjustment=0.0)


async def test_record_overwrites_same_id_to_set_outcome() -> None:
    memory = EpisodicMemory(store=InMemoryVectorStore())
    features = make_features()
    for index in range(5):
        correlation_id = f"x{index}"
        await memory.record(
            Episode(correlation_id=correlation_id, symbol="XAUUSD", features=features, decision="BUY")
        )
        await memory.record(
            Episode(
                correlation_id=correlation_id,
                symbol="XAUUSD",
                features=features,
                decision="BUY",
                outcome=1.0,
            )
        )
    recall = await memory.recall(features)
    assert recall.samples == 5
    assert recall.win_rate == pytest.approx(1.0)


def test_vectorizer_deterministic_and_bounded() -> None:
    vectorizer = FeatureVectorizer(dimension=128)
    first = vectorizer.vectorize(make_features())
    second = vectorizer.vectorize(make_features())
    assert first == second
    assert all(-1.0 <= value <= 1.0 for value in first)


def test_vectorizer_ignores_non_finite_values() -> None:
    vectorizer = FeatureVectorizer()
    features = make_features()
    features["confidence"] = float("nan")
    vector = vectorizer.vectorize(features)
    assert len(vector) == 128
    assert all(-1.0 <= value <= 1.0 for value in vector)
