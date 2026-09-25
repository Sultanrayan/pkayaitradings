"""Tests for the developer agent API."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from orchestrator import main as orchestrator_main
from orchestrator.dev_api import DISCLAIMER


def make_bars(n: int = 200, drift: float = 0.5, seed: int = 7) -> list[dict[str, object]]:
    rng = np.random.default_rng(seed)
    close = 100.0 + np.cumsum(rng.normal(drift, 0.4, n))
    start = datetime(2026, 1, 1, tzinfo=UTC)
    return [
        {
            "open_time": (start + timedelta(hours=i)).isoformat(),
            "open": float(close[i] - 0.2),
            "high": float(close[i] + 0.5),
            "low": float(close[i] - 0.5),
            "close": float(close[i]),
            "tick_volume": 100 + i,
        }
        for i in range(n)
    ]


@pytest.fixture
async def client():
    import httpx

    transport = httpx.ASGITransport(app=orchestrator_main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client


async def test_capabilities(client) -> None:
    response = await client.get("/api/v1/agents/capabilities")
    assert response.status_code == 200
    body = response.json()
    assert body["disclaimer"] == DISCLAIMER
    assert "AI/ML model weights" in body["does_not_provide"]
    assert "technical_analyst" in body["agents"]
    assert any("Kelly" in strategy for strategy in body["strategies"])


async def test_technical_endpoint(client) -> None:
    response = await client.post(
        "/api/v1/agents/technical",
        json={"symbol": "XAUUSD", "timeframe": "H1", "bars": make_bars(200, drift=0.6)},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["signal"] == "BULLISH"
    assert body["agent"] == "technical_analyst"
    assert body["indicators"]["rsi"] is not None


async def test_technical_rejects_too_few_bars(client) -> None:
    response = await client.post(
        "/api/v1/agents/technical",
        json={"symbol": "XAUUSD", "bars": make_bars(10)},
    )
    assert response.status_code == 422


async def test_news_endpoint_from_headlines(client) -> None:
    response = await client.post(
        "/api/v1/agents/news",
        json={"symbol": "BTCUSD", "headlines": ["Bitcoin rallies on record ETF inflows"]},
    )
    assert response.status_code == 200
    assert response.json()["sentiment"] in {"BULLISH", "VERY_BULLISH"}


async def test_news_endpoint_accepts_supplied_sentiment(client) -> None:
    response = await client.post(
        "/api/v1/agents/news",
        json={"symbol": "XAUUSD", "sentiment": "BEARISH", "confidence": 0.8},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["sentiment"] == "BEARISH"
    assert body["confidence"] == 0.8


async def test_risk_endpoint(client) -> None:
    response = await client.post(
        "/api/v1/agents/risk",
        json={
            "symbol": "XAUUSD",
            "direction": "BULLISH",
            "entry_price": 2650.0,
            "confidence": 0.7,
            "atr": 10.0,
            "equity": 100_000.0,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["approved"] is True
    assert body["position_size"] > 0


async def test_risk_endpoint_vetoes_on_drawdown(client) -> None:
    response = await client.post(
        "/api/v1/agents/risk",
        json={
            "symbol": "XAUUSD",
            "direction": "BULLISH",
            "entry_price": 2650.0,
            "confidence": 0.7,
            "atr": 10.0,
            "equity": 90_000.0,
            "peak_equity": 100_000.0,
        },
    )
    assert response.status_code == 200
    assert response.json()["approved"] is False


async def test_decide_endpoint(client) -> None:
    technical = (
        await client.post(
            "/api/v1/agents/technical",
            json={"symbol": "XAUUSD", "timeframe": "H1", "bars": make_bars(200, drift=0.6)},
        )
    ).json()
    news = (
        await client.post(
            "/api/v1/agents/news",
            json={"symbol": "XAUUSD", "headlines": ["Gold rallies to a record high"]},
        )
    ).json()
    risk = (
        await client.post(
            "/api/v1/agents/risk",
            json={
                "symbol": "XAUUSD",
                "direction": "BULLISH",
                "entry_price": 2650.0,
                "confidence": 0.7,
                "atr": 10.0,
                "equity": 100_000.0,
            },
        )
    ).json()

    response = await client.post(
        "/api/v1/agents/decide",
        json={"technical": technical, "news": news, "risk": risk},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["decision"] in {"BUY", "SELL", "WAIT", "SKIP"}
    assert body["risk_approved"] is True


async def test_analyze_endpoint(client) -> None:
    response = await client.post(
        "/api/v1/agents/analyze",
        json={
            "symbol": "XAUUSD",
            "timeframe": "H1",
            "bars": make_bars(200, drift=0.6),
            "headlines": ["Gold rallies on dovish Fed"],
            "equity": 100_000.0,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "XAUUSD"
    assert body["technical"]["signal"] == "BULLISH"
    assert body["decision"]["decision"] in {"BUY", "SELL", "WAIT", "SKIP"}
    assert body["disclaimer"] == DISCLAIMER
