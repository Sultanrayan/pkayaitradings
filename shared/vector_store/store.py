"""News embedding and vector search.

A dependency-free in-memory store is the default; a Qdrant-backed store is used
when ``qdrant-client`` is installed and configured. Embeddings default to a
deterministic hashing embedder so the system works without any external model.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from shared.config import Settings, get_settings
from shared.logging import get_logger

_logger = get_logger(__name__)


@runtime_checkable
class Embedder(Protocol):
    """Turn text into dense vectors."""

    @property
    def dimension(self) -> int:
        """Embedding dimensionality."""

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts."""


class HashingEmbedder:
    """Deterministic bag-of-words hashing embedder.

    Useful as an offline default and for tests. It is not a semantic model; it
    provides lexical similarity only.
    """

    def __init__(self, dimension: int = 256) -> None:
        self._dimension = dimension

    @property
    def dimension(self) -> int:
        return self._dimension

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self._dimension
        for token in text.lower().split():
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self._dimension
            vector[index] += 1.0
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0.0:
            return vector
        return [value / norm for value in vector]


@dataclass(frozen=True)
class SearchResult:
    """A single vector-search hit."""

    id: str
    score: float
    payload: dict[str, object]


@runtime_checkable
class VectorStore(Protocol):
    """Minimal vector-store interface for news search."""

    async def upsert(
        self, ids: list[str], vectors: list[list[float]], payloads: list[dict[str, object]]
    ) -> None:
        """Insert or update vectors with payloads."""

    async def search(self, vector: list[float], *, limit: int = 5) -> list[SearchResult]:
        """Return the nearest neighbours to ``vector``."""


class InMemoryVectorStore:
    """Brute-force cosine-similarity vector store."""

    def __init__(self) -> None:
        self._items: dict[str, tuple[list[float], dict[str, object]]] = {}

    async def upsert(
        self, ids: list[str], vectors: list[list[float]], payloads: list[dict[str, object]]
    ) -> None:
        for item_id, vector, payload in zip(ids, vectors, payloads, strict=True):
            self._items[item_id] = (vector, payload)

    async def search(self, vector: list[float], *, limit: int = 5) -> list[SearchResult]:
        scored = [
            SearchResult(id=item_id, score=_cosine(vector, stored), payload=payload)
            for item_id, (stored, payload) in self._items.items()
        ]
        scored.sort(key=lambda result: result.score, reverse=True)
        return scored[:limit]


class QdrantVectorStore:
    """Qdrant-backed vector store.

    Args:
        url: Qdrant endpoint.
        collection: Collection name.
        dimension: Vector dimensionality.
        api_key: Optional Qdrant API key.
    """

    def __init__(
        self, url: str, collection: str, dimension: int, *, api_key: str | None = None
    ) -> None:
        self._url = url
        self._collection = collection
        self._dimension = dimension
        self._api_key = api_key
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        from qdrant_client import QdrantClient

        client = QdrantClient(url=self._url, api_key=self._api_key)
        self._ensure_collection(client)
        self._client = client
        return client

    def _ensure_collection(self, client: Any) -> None:
        from qdrant_client.models import Distance, VectorParams

        existing = {collection.name for collection in client.get_collections().collections}
        if self._collection not in existing:
            client.create_collection(
                collection_name=self._collection,
                vectors_config=VectorParams(size=self._dimension, distance=Distance.COSINE),
            )

    async def upsert(
        self, ids: list[str], vectors: list[list[float]], payloads: list[dict[str, object]]
    ) -> None:
        from qdrant_client.models import PointStruct

        client = self._get_client()
        points = [
            PointStruct(id=item_id, vector=vector, payload=payload)
            for item_id, vector, payload in zip(ids, vectors, payloads, strict=True)
        ]
        client.upsert(collection_name=self._collection, points=points)

    async def search(self, vector: list[float], *, limit: int = 5) -> list[SearchResult]:
        client = self._get_client()
        hits = client.search(collection_name=self._collection, query_vector=vector, limit=limit)
        return [
            SearchResult(id=str(hit.id), score=float(hit.score), payload=hit.payload or {})
            for hit in hits
        ]


def build_vector_store(
    settings: Settings | None = None,
    *,
    embedder: Embedder | None = None,
) -> tuple[VectorStore, Embedder]:
    """Return the best available vector store and embedder.

    Falls back to the in-memory store when Qdrant is not installed.
    """
    settings = settings or get_settings()
    embedder = embedder or HashingEmbedder()
    try:
        import qdrant_client  # noqa: F401 - optional dependency

        return (
            QdrantVectorStore(
                settings.qdrant_url,
                collection="news",
                dimension=embedder.dimension,
                api_key=settings.qdrant_api_key,
            ),
            embedder,
        )
    except ImportError:
        _logger.info("vector_store.in_memory_fallback")
        return InMemoryVectorStore(), embedder


def _cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        raise ValueError("Vector dimensions do not match")
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return dot / (left_norm * right_norm)
