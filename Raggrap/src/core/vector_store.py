"""Vector search adapters for semantic correction retrieval."""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any, Protocol

from ..models.schemas import Mistake

_TOKEN = re.compile(r"[a-zA-Z0-9_'-]+")


def _tokens(value: str) -> Counter[str]:
    return Counter(token.casefold() for token in _TOKEN.findall(value))


def _cosine(left: Counter[str], right: Counter[str]) -> float:
    if not left or not right:
        return 0.0
    dot_product = sum(count * right[token] for token, count in left.items())
    magnitude = math.sqrt(sum(count * count for count in left.values())) * math.sqrt(
        sum(count * count for count in right.values())
    )
    return dot_product / magnitude if magnitude else 0.0


class VectorStore(Protocol):
    """Common interface for vector stores."""

    def add_mistake(self, mistake_id: str, mistake: Mistake) -> None: ...

    def search(self, query: str, limit: int) -> list[dict[str, Any]]: ...


class InMemoryVectorStore:
    """TF-IDF-free bag-of-words cosine store (no external dependencies)."""

    def __init__(self) -> None:
        self._documents: dict[str, tuple[Counter[str], dict[str, Any]]] = {}

    def add_mistake(self, mistake_id: str, mistake: Mistake) -> None:
        document = f"{mistake.concept} {mistake.description} {mistake.rule}"
        self._documents[mistake_id] = (
            _tokens(document),
            {
                "mistake_id": mistake_id,
                "mistake": mistake.description,
                "description": mistake.description,
                "rule": mistake.rule,
                "concept": mistake.concept,
                "severity": mistake.severity.value,
                "query": mistake.query,
                "wrong_answer": mistake.wrong_answer,
                "correct_answer": mistake.correct_answer,
                "query_pattern": mistake.query_pattern,
                "timestamp": mistake.timestamp,
            },
        )

    def search(self, query: str, limit: int) -> list[dict[str, Any]]:
        query_tokens = _tokens(query)
        scored = [
            (
                {**metadata, "similarity": _cosine(query_tokens, tokens)},
                _cosine(query_tokens, tokens),
            )
            for tokens, metadata in self._documents.values()
        ]
        return [
            item
            for item, score in sorted(scored, key=lambda entry: entry[1], reverse=True)[:limit]
            if score > 0
        ]


class ChromaVectorStore:
    """ChromaDB-backed vector store (falls back to in-memory when unavailable)."""

    def __init__(self, collection: Any) -> None:
        self._collection = collection

    def add_mistake(self, mistake_id: str, mistake: Mistake) -> None:
        self._collection.upsert(
            ids=[mistake_id],
            documents=[f"{mistake.concept} {mistake.description} {mistake.rule}"],
            metadatas=[
                {
                    "concept": mistake.concept,
                    "mistake": mistake.description,
                    "rule": mistake.rule,
                    "severity": mistake.severity.value,
                }
            ],
        )

    def search(self, query: str, limit: int) -> list[dict[str, Any]]:
        result = self._collection.query(query_texts=[query], n_results=limit)
        records: list[dict[str, Any]] = []
        for index, metadata in enumerate(result.get("metadatas", [[]])[0]):
            record = dict(metadata or {})
            record["mistake_id"] = result.get("ids", [[]])[0][index]
            distances = result.get("distances", [[]])[0]
            record["similarity"] = 1 - distances[index] if index < len(distances) else 0
            records.append(record)
        return records


def create_vector_store(settings: Any) -> VectorStore:
    try:
        if not settings.enable_vector_search:
            return InMemoryVectorStore()
        import chromadb

        client = chromadb.PersistentClient(path=settings.chroma_persist_dir)
        collection = client.get_or_create_collection(settings.chroma_collection_name)
        return ChromaVectorStore(collection)
    except Exception:
        return InMemoryVectorStore()
