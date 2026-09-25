"""Vector store integration for news embeddings."""

from shared.vector_store.store import (
    Embedder,
    HashingEmbedder,
    InMemoryVectorStore,
    QdrantVectorStore,
    SearchResult,
    VectorStore,
    build_vector_store,
)

__all__ = [
    "Embedder",
    "HashingEmbedder",
    "InMemoryVectorStore",
    "QdrantVectorStore",
    "SearchResult",
    "VectorStore",
    "build_vector_store",
]
