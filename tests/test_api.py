"""Tests for the FastAPI gateway using an in-process ASGI transport."""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI

from orchestrator.main import app
from shared.config import Settings
from tests.test_pipeline import _build_pipeline
from tests.test_strategy import make_series


@pytest.fixture
def configured_app(settings: Settings) -> FastAPI:
    pipeline = _build_pipeline(settings, make_series(300, drift=0.6))
    app.state.pipeline = pipeline
    app.state.settings = settings
    return app


@pytest.fixture
async def client(configured_app: FastAPI) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=configured_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client


async def test_health(client: httpx.AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "XAUUSD" in body["symbols"]


async def test_tick_endpoint(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/tick/XAUUSD")
    assert response.status_code == 200
    assert response.json()["symbol"] == "XAUUSD"


async def test_ohlc_endpoint(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/ohlc/XAUUSD", params={"interval": "H1", "limit": 10})
    assert response.status_code == 200
    assert response.json()["symbol"] == "XAUUSD"


async def test_analyze_endpoint(client: httpx.AsyncClient) -> None:
    headers = await _auth_headers(client, "analyze@example.com")
    response = await client.post("/api/v1/analyze/XAUUSD", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "XAUUSD"
    assert body["decision"]["decision"] in {"BUY", "SELL", "WAIT", "SKIP"}
    assert body["technical"]["signal"] == "BULLISH"


async def test_v1_analysis_endpoint(client: httpx.AsyncClient) -> None:
    headers = await _auth_headers(client, "v1-analysis@example.com")
    response = await client.post("/v1/analysis", json={"symbol": "XAUUSD"}, headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "XAUUSD"
    assert body["decision"]["decision"] in {"BUY", "SELL", "WAIT", "SKIP"}
    assert "technical" in body and "news" in body and "risk" in body and "decision" in body


async def test_v1_analysis_requires_symbol(client: httpx.AsyncClient) -> None:
    headers = await _auth_headers(client, "v1-analysis-bad@example.com")
    response = await client.post("/v1/analysis", json={"symbol": ""}, headers=headers)
    assert response.status_code == 422


async def test_analyze_rejects_bad_timeframe(client: httpx.AsyncClient) -> None:
    headers = await _auth_headers(client, "analyze-bad@example.com")
    response = await client.post(
        "/api/v1/analyze/XAUUSD", params={"timeframes": "BAD"}, headers=headers
    )
    assert response.status_code == 422


async def _auth_headers(client: httpx.AsyncClient, email: str) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/register",
        json={"name": "API", "email": email, "password": "supersecret"},
    )
    if response.status_code == 400:  # already registered by an earlier test
        response = await client.post(
            "/api/v1/auth/login", json={"email": email, "password": "supersecret"}
        )
    assert response.status_code in {200, 201}
    return {"Authorization": f"Bearer {response.json()['token']}"}


async def test_positions_and_equity(client: httpx.AsyncClient) -> None:
    positions = await client.get("/api/v1/positions")
    equity = await client.get("/api/v1/equity")
    assert positions.status_code == 200
    assert equity.status_code == 200
    assert equity.json() > 0


async def test_batch_analyze(client: httpx.AsyncClient) -> None:
    headers = await _auth_headers(client, "batch@example.com")
    response = await client.post("/api/v1/analyze", json={"symbols": ["XAUUSD", "BTCUSD"]}, headers=headers)
    assert response.status_code == 200
    assert len(response.json()) == 2
