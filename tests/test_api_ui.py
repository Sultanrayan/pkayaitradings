"""Tests for the UI-facing endpoints (signals, agents, performance, news)."""

from __future__ import annotations

from dataclasses import dataclass, field

import httpx
import pytest
from fastapi import FastAPI

from orchestrator import main as orchestrator_main
from orchestrator.store import SignalStore
from shared.config import Settings
from shared.schemas.enums import (
    AlertLevel,
    Decision,
    Direction,
    Impact,
    Sentiment,
    Timeframe,
)
from shared.schemas.market import (
    CalendarEvent,
    MarketMover,
    MarketSummary,
    NewsArticle,
)
from shared.schemas.signals import (
    NewsSignal,
    RiskAssessment,
    TechnicalSignal,
    TradeDecision,
)
from shared.utils.time import utcnow


class _FakeClient:
    async def get_news(
        self, *, symbol: str | None = None, max_results: int = 10
    ) -> list[NewsArticle]:
        return [NewsArticle(title="Gold rallies", url="https://example.com/a", publisher="Reuters")]

    async def get_calendar(
        self,
        *,
        importance: Impact | None = None,
        countries: list[str] | None = None,
        limit: int = 100,
    ) -> list[CalendarEvent]:
        return [
            CalendarEvent(
                id="mql5:1",
                eventId="mql5:840",
                time=utcnow(),
                countryCode="US",
                currency="USD",
                name="Nonfarm Payrolls",
                importance=Impact.HIGH,
            )
        ]

    async def get_market_movers(self, kind: str, *, limit: int = 10) -> list[MarketMover]:
        return [MarketMover(symbol="XAUUSD", lastPrice=2650.0, changePercent=1.2)]

    async def get_market_summary(self) -> MarketSummary:
        return MarketSummary()


@dataclass
class _FakePipeline:
    store: SignalStore = field(default_factory=SignalStore)
    client: _FakeClient = field(default_factory=_FakeClient)
    settings: Settings = field(default_factory=Settings)
    decision: object = None


def _populate(store: SignalStore) -> None:
    store.record_cycle(
        symbol="XAUUSD",
        correlation_id="c1",
        technical=TechnicalSignal(
            symbol="XAUUSD",
            timeframe=Timeframe.H1,
            signal=Direction.BULLISH,
            confidence=0.8,
        ),
        news=NewsSignal(
            event="FOMC",
            impact=Impact.HIGH,
            sentiment=Sentiment.BEARISH,
            confidence=0.6,
            alert=AlertLevel.REDUCE_POSITION_SIZE,
        ),
        risk=RiskAssessment(symbol="XAUUSD", approved=True, position_size=1.0),
        decision=TradeDecision(
            symbol="XAUUSD",
            decision=Decision.BUY,
            final_score=0.7,
            technical_score=0.8,
            news_score=0.4,
            risk_score=1.0,
            risk_approved=True,
            executed=True,
        ),
    )


@pytest.fixture
def configured_app(settings: Settings) -> FastAPI:
    pipeline = _FakePipeline(settings=settings)
    _populate(pipeline.store)
    orchestrator_main.app.state.pipeline = pipeline
    orchestrator_main.app.state.settings = settings
    return orchestrator_main.app


@pytest.fixture
async def client(configured_app: FastAPI) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=configured_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client


async def test_signals_endpoint(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/signals")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 4
    assert {"id", "agent", "direction", "confidence", "payload"} <= set(body[0])


async def test_signals_filters(client: httpx.AsyncClient) -> None:
    response = await client.get(
        "/api/v1/signals", params={"agent": "technical_analyst", "min_confidence": 0.5}
    )
    assert response.status_code == 200
    assert len(response.json()) == 1


async def test_agents_endpoint(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/agents")
    assert response.status_code == 200
    names = {entry["name"] for entry in response.json()}
    assert names == {
        "technical_analyst",
        "news_monitor",
        "risk_manager",
        "decision_maker",
    }


async def test_performance_endpoint(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/performance")
    assert response.status_code == 200
    body = response.json()
    assert body["total_signals"] == 4
    assert body["decisions"]["BUY"] == 1


async def test_alerts_endpoint(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/alerts")
    assert response.status_code == 200
    assert any(alert["type"] == "news" for alert in response.json())


async def test_news_endpoint(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/news", params={"symbol": "XAUUSD"})
    assert response.status_code == 200
    assert response.json()[0]["title"] == "Gold rallies"


async def test_calendar_endpoint(client: httpx.AsyncClient) -> None:
    response = await client.get(
        "/api/v1/calendar", params={"importance": "high", "countries": "us,eu"}
    )
    assert response.status_code == 200
    assert response.json()[0]["name"] == "Nonfarm Payrolls"


async def test_calendar_rejects_bad_importance(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/calendar", params={"importance": "nope"})
    assert response.status_code == 422


async def test_market_endpoints(client: httpx.AsyncClient) -> None:
    movers = await client.get("/api/v1/market/movers", params={"kind": "gainers"})
    summary = await client.get("/api/v1/market/summary")
    assert movers.status_code == 200
    assert movers.json()[0]["symbol"] == "XAUUSD"
    assert summary.status_code == 200


async def test_market_movers_rejects_bad_kind(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/market/movers", params={"kind": "bogus"})
    assert response.status_code == 422
