"""Tests that the API surface is not published to the browser by default."""

from __future__ import annotations

import httpx
import pytest

from orchestrator import main as orchestrator_main


@pytest.fixture
async def client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=orchestrator_main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client


async def test_api_docs_are_not_exposed(client: httpx.AsyncClient) -> None:
    """FastAPI's docs and schema must not be reachable unless explicitly enabled."""
    for path in ("/docs", "/redoc", "/openapi.json"):
        response = await client.get(path)
        assert response.status_code == 404, f"{path} should be hidden"


async def test_health_still_public(client: httpx.AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
