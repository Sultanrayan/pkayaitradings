"""Episodic memory for trading decisions (backend-v2, Problem 8).

Every decision is stored as a vector in the shared vector store together with
its (eventual) outcome. Before a new decision the Decision Maker recalls the
most similar past situations and adjusts confidence by the historical win rate,
so the system "learns from its mistakes" without repeating the same mistake.

A Qdrant-backed store is used when ``qdrant-client`` is installed and
configured; otherwise an in-memory store (process-local) keeps the feature
working offline and in tests.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Any

from shared.config import Settings, get_settings
from shared.logging import get_logger
from shared.vector_store.store import InMemoryVectorStore, QdrantVectorStore, VectorStore

_logger = get_logger(__name__)

_BUCKETS = 8
_DEFAULT_DIMENSION = 128


@dataclass(frozen=True)
class Episode:
    """A stored decision and its outcome."""

    correlation_id: str
    symbol: str
    features: dict[str, float]
    decision: str
    outcome: float | None = None


@dataclass(frozen=True)
class MemoryRecall:
    """Result of recalling similar past situations."""

    samples: int
    win_rate: float | None
    adjustment: float


class FeatureVectorizer:
    """Deterministic vectoriser for numeric situation features.

    Each ``(feature, value-bucket)`` pair hashes to a signed unit contribution,
    so episodes in the same regime with similar indicator values end up with
    similar (cosine-similar) vectors.
    """

    def __init__(self, dimension: int = _DEFAULT_DIMENSION) -> None:
        self._dimension = dimension

    @property
    def dimension(self) -> int:
        return self._dimension

    def vectorize(self, features: dict[str, float]) -> list[float]:
        vector = [0.0] * self._dimension
        for name, value in features.items():
            if value is None or not math.isfinite(value):
                continue
            bucket = int(((max(-1.0, min(1.0, value)) + 1.0) / 2.0) * _BUCKETS)
            bucket = max(0, min(_BUCKETS - 1, bucket))
            key = f"{name}:{bucket}"
            digest = hashlib.sha256(key.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self._dimension
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0.0:
            return vector
        return [value / norm for value in vector]


class EpisodicMemory:
    """Records decisions and recalls similar situations with win-rate scoring."""

    def __init__(
        self,
        *,
        store: VectorStore | None = None,
        vectorizer: FeatureVectorizer | None = None,
        settings: Settings | None = None,
        max_samples: int = 10_000,
    ) -> None:
        self.settings = settings or get_settings()
        self.vectorizer = vectorizer or FeatureVectorizer()
        self.store = store or self._build_store()
        self._max_samples = max_samples
        self._count = 0

    def _build_store(self) -> VectorStore:
        try:
            import qdrant_client  # noqa: F401 - optional dependency

            return QdrantVectorStore(
                self.settings.qdrant_url,
                collection="episodes",
                dimension=self.vectorizer.dimension,
                api_key=self.settings.qdrant_api_key,
            )
        except ImportError:
            _logger.info("episodic_memory.in_memory_fallback")
            return InMemoryVectorStore()

    async def recall(
        self, features: dict[str, float], *, k: int | None = None, min_samples: int | None = None
    ) -> MemoryRecall:
        """Return the win-rate of the most similar past situations.

        The adjustment is bounded by ``memory_score_adjustment_max`` and is
        ``0.0`` when there are fewer than ``min_samples`` resolved episodes.
        This method never raises.
        """
        k = k or self.settings.memory_recall_k
        min_samples = min_samples or self.settings.memory_min_samples
        try:
            vector = self.vectorizer.vectorize(features)
            hits = await self.store.search(vector, limit=max(k, min_samples))
        except Exception as exc:
            _logger.warning("episodic_memory.recall_failed", error=repr(exc))
            return MemoryRecall(samples=0, win_rate=None, adjustment=0.0)

        outcomes: list[float] = []
        for hit in hits:
            outcome = hit.payload.get("outcome")
            if isinstance(outcome, (int, float)):
                outcomes.append(float(outcome))
        if len(outcomes) < min_samples:
            return MemoryRecall(samples=len(outcomes), win_rate=None, adjustment=0.0)

        wins = sum(1 for outcome in outcomes if outcome > 0)
        win_rate = wins / len(outcomes)
        return MemoryRecall(
            samples=len(outcomes),
            win_rate=win_rate,
            adjustment=self._adjustment(win_rate),
        )

    def _adjustment(self, win_rate: float) -> float:
        maximum = self.settings.memory_score_adjustment_max
        return float(max(-maximum, min(maximum, (win_rate - 0.5) * 2.0 * maximum)))

    async def record(self, episode: Episode) -> None:
        """Store an episode. Overwrites a prior episode with the same id
        (used to attach a resolved outcome). Never raises.
        """
        if self._max_samples and self._count >= self._max_samples:
            _logger.debug("episodic_memory.capacity_reached")
            return
        try:
            vector = self.vectorizer.vectorize(episode.features)
            payload: dict[str, Any] = {
                "symbol": episode.symbol,
                "decision": episode.decision,
                "outcome": episode.outcome,
            }
            await self.store.upsert(
                [episode.correlation_id], [vector], [payload]
            )
            self._count += 1
        except Exception as exc:
            _logger.warning("episodic_memory.record_failed", error=repr(exc))


def build_episodic_memory(settings: Settings | None = None) -> EpisodicMemory:
    """Build an episodic memory from settings, falling back to in-memory."""
    return EpisodicMemory(settings=settings or get_settings())
