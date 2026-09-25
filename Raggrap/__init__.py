"""AI Self-Improvement Engine with GraphRAG.

An engine that answers queries while retrieving and applying recorded
corrections from past mistakes (graph + vector hybrid retrieval).
"""

from __future__ import annotations

from .src.core.graph_rag import GraphRAGEngine
from .src.core.graph_store import InMemoryGraphStore, Neo4jGraphStore
from .src.core.vector_store import InMemoryVectorStore
from .src.models.schemas import (
    EvaluationResult,
    HealthResponse,
    Mistake,
    MistakeRecord,
    QueryRequest,
    QueryResponse,
    Rule,
    SeverityLevel,
    StatisticsResponse,
)

__all__ = [
    "EvaluationResult",
    "GraphRAGEngine",
    "HealthResponse",
    "InMemoryGraphStore",
    "InMemoryVectorStore",
    "Mistake",
    "MistakeRecord",
    "Neo4jGraphStore",
    "QueryRequest",
    "QueryResponse",
    "Rule",
    "SeverityLevel",
    "StatisticsResponse",
]
