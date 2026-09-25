"""Tests for the Raggrap API mounted into the backend FastAPI app."""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI

from orchestrator.main import app
from orchestrator.raggrap import build_raggrap_engine
from Raggrap.src.core.entity_extractor import EntityExtractor
from Raggrap.src.core.graph_rag import GraphRAGEngine
from Raggrap.src.core.graph_store import InMemoryGraphStore
from Raggrap.src.core.llm import DeterministicProvider
from Raggrap.src.core.vector_store import InMemoryVectorStore
from shared.config import Settings


def _test_engine(settings: Settings) -> GraphRAGEngine:
    """Deterministic, in-memory engine that never touches the network."""
    config = build_raggrap_engine(settings).config
    return GraphRAGEngine(
        config,
        graph_store=InMemoryGraphStore(),
        vector_store=InMemoryVectorStore(),
        main_llm=DeterministicProvider(),
        critic_llm=DeterministicProvider(critic=True),
        entity_extractor=EntityExtractor("unused"),
    )


@pytest.fixture
def configured_app(settings: Settings) -> FastAPI:
    app.state.pipeline = None  # type: ignore[assignment]
    app.state.settings = settings
    app.state.rag_engine = _test_engine(settings)
    return app


@pytest.fixture
async def client(configured_app: FastAPI) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=configured_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client


async def test_raggrap_health(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/raggrap/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["graph_store"] == "InMemoryGraphStore"
    assert body["llm_provider"] == "DeterministicProvider"


async def test_raggrap_query(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/v1/raggrap/query",
        json={"query": "Is Python for frontend?", "use_cache": False},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["query"] == "Is Python for frontend?"
    assert body["answer"]
    assert body["was_corrected"] is False


async def test_raggrap_record_and_retrieve_mistake(client: httpx.AsyncClient) -> None:
    record = await client.post(
        "/api/v1/raggrap/mistakes",
        json={
            "concept": "Python",
            "description": "Suggested python for the UI",
            "rule": "Use JS/TS for the frontend; Python serves the backend.",
            "query": "python frontend",
            "query_pattern": "python frontend",
        },
    )
    assert record.status_code == 201
    mistake_id = record.json()["mistake_id"]
    assert mistake_id.startswith("mistake_")

    listed = await client.get("/api/v1/raggrap/mistakes")
    assert listed.status_code == 200
    assert any(item["mistake_id"] == mistake_id for item in listed.json())


async def test_raggrap_statistics_and_cache_clear(client: httpx.AsyncClient) -> None:
    await client.post(
        "/api/v1/raggrap/mistakes",
        json={"concept": "X", "description": "d", "rule": "r"},
    )
    stats = await client.get("/api/v1/raggrap/statistics")
    assert stats.status_code == 200
    assert stats.json()["total_mistakes"] == 1

    cleared = await client.post("/api/v1/raggrap/cache/clear")
    assert cleared.status_code == 200
    assert cleared.json()["cleared"] is True
