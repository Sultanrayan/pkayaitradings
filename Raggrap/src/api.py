"""FastAPI REST API for the GraphRAG engine.

Exposes query, correction-recording, cache and health endpoints described in
the research document ("API Framework: FastAPI | REST API deployment").
"""

from __future__ import annotations

from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, Query, Request, status
from pydantic import BaseModel, Field

from ..config.settings import Settings, settings
from .core.graph_rag import GraphRAGEngine
from .models.schemas import (
    HealthResponse,
    Mistake,
    MistakeRecord,
    QueryRequest,
    QueryResponse,
    StatisticsResponse,
)

router = APIRouter(prefix="/api/v1/raggrap", tags=["raggrap"])


class RecordResponse(BaseModel):
    """Identifier returned after a correction is recorded."""

    mistake_id: str = Field(..., description="Stable identifier for the recorded mistake")


def _resolve_engine(request: Request) -> GraphRAGEngine:
    engine = getattr(request.app.state, "rag_engine", None)
    if engine is None:
        # Lazy default (e.g. tests/standalone that skip the lifespan): keep the
        # API usable by constructing the standard in-memory engine once.
        engine = create_engine()
        request.app.state.rag_engine = engine
    return cast(GraphRAGEngine, engine)


EngineDep = Annotated[GraphRAGEngine, Depends(_resolve_engine)]


@router.get("/health", response_model=HealthResponse, tags=["raggrap"])
async def health(engine: EngineDep) -> HealthResponse:
    """Report the engine's backing stores and live provider."""
    return HealthResponse(**engine.health_check())


@router.post("/query", response_model=QueryResponse, tags=["raggrap"])
async def query(body: QueryRequest, engine: EngineDep) -> QueryResponse:
    """Answer a query, applying recorded corrections from past mistakes."""
    return engine.answer(
        body.query,
        use_cache=body.use_cache,
        include_reasoning=body.include_explanation,
    )


@router.post(
    "/mistakes",
    response_model=RecordResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["raggrap"],
)
async def record_mistake(body: Mistake, engine: EngineDep) -> RecordResponse:
    """Record a correction so future queries can avoid the same mistake."""
    return RecordResponse(mistake_id=engine.record_mistake(body))


@router.get("/mistakes", response_model=list[MistakeRecord], tags=["raggrap"])
async def list_mistakes(
    engine: EngineDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[MistakeRecord]:
    """Return recorded mistakes/corrections (newest last)."""
    records = engine.get_mistakes(limit)
    return [
        MistakeRecord(
            mistake_id=record["mistake_id"],
            concept=record.get("concept", ""),
            description=record.get("description", record.get("mistake", "")),
            rule=record.get("rule", ""),
            severity=record.get("severity", "medium"),
            query=record.get("query"),
            wrong_answer=record.get("wrong_answer"),
            correct_answer=record.get("correct_answer"),
            query_pattern=record.get("query_pattern"),
            timestamp=record.get("timestamp"),
            corrected_count=record.get("corrected_count", 0),
        )
        for record in records
    ]


@router.get("/statistics", response_model=StatisticsResponse, tags=["raggrap"])
async def statistics(engine: EngineDep) -> StatisticsResponse:
    """Return learning progress metrics (concepts/mistakes/rules/applications)."""
    return StatisticsResponse(**engine.get_statistics())


@router.post("/cache/clear", tags=["raggrap"])
async def clear_cache(engine: EngineDep) -> dict[str, bool]:
    """Flush cached responses."""
    engine.clear_cache()
    return {"cleared": True}


def create_engine(config: Settings | None = None, **kwargs: Any) -> GraphRAGEngine:
    """Construct a :class:`GraphRAGEngine` with the default (or given) config."""
    return GraphRAGEngine(config or settings, **kwargs)
