"""Tests for the market-aware chat endpoint backing the ``/ai`` page."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from orchestrator import chat as chat_module
from orchestrator.main import app
from shared.config import Settings
from shared.schemas.market import NewsArticle, OhlcBar, OhlcSeries, Tick
from tests.test_pipeline import _build_pipeline
from tests.test_strategy import make_series

_START = datetime(2026, 1, 1, tzinfo=UTC)


class _StubLLM:
    """Stands in for the chat model, recording the prompt it was handed."""

    def __init__(self) -> None:
        self.model = "stub-chat-model"
        self.prompts: list[str] = []
        self.systems: list[str | None] = []

    async def complete(self, prompt: str, *, system: str | None = None) -> str:
        self.prompts.append(prompt)
        self.systems.append(system)
        return "Gold is holding above its 20-period average on the H1 window."


def _tick() -> Tick:
    return Tick(
        symbol="XAUUSD",
        bid=2640.10,
        ask=2640.30,
        mid=2640.20,
        spread=0.20,
        high=2651.00,
        low=2632.00,
        direction="UP",
        timestamp=_START + timedelta(hours=5),
    )


def _series(bars: int = 60) -> OhlcSeries:
    return OhlcSeries(
        symbol="XAUUSD",
        interval="1h",
        bars=tuple(
            OhlcBar(
                openTime=_START + timedelta(hours=index),
                open=2600.0 + index,
                high=2605.0 + index,
                low=2595.0 + index,
                close=2602.0 + index,
            )
            for index in range(bars)
        ),
    )


def _news() -> list[NewsArticle]:
    return [
        NewsArticle(
            title="Gold steadies as traders await inflation print",
            url="https://example.test/gold",
            publisher="Example Wire",
        )
    ]


@pytest.fixture
def stub_llm(monkeypatch: pytest.MonkeyPatch) -> _StubLLM:
    """Replace the chat model so no network call is ever made."""
    stub = _StubLLM()
    monkeypatch.setattr(chat_module, "build_chat_llm_client", lambda _settings: stub)
    return stub


@pytest.fixture
def configured_app(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    pipeline = _build_pipeline(settings, make_series(300, drift=0.6))

    async def _get_tick(symbol: str, **_: Any) -> Tick:
        return _tick()

    async def _get_ohlc(symbol: str, **_: Any) -> OhlcSeries:
        return _series()

    async def _get_news(**_: Any) -> list[NewsArticle]:
        return _news()

    # ``raising=False``: the shared pipeline stub only implements part of the
    # market client's surface, and these attributes are being added to it here.
    monkeypatch.setattr(pipeline.client, "get_tick", _get_tick, raising=False)
    monkeypatch.setattr(pipeline.client, "get_ohlc", _get_ohlc, raising=False)
    monkeypatch.setattr(pipeline.client, "get_news", _get_news, raising=False)

    app.state.pipeline = pipeline
    app.state.settings = settings
    return app


@pytest.fixture
async def client(configured_app: FastAPI) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=configured_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client


async def test_chat_requires_a_configured_model(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With no chat key the endpoint reports 503 instead of inventing an answer."""
    monkeypatch.setattr(chat_module, "build_chat_llm_client", lambda _settings: None)
    response = await client.post("/api/v1/chat", json={"question": "Where is gold?"})
    assert response.status_code == 503
    assert "CHAT_LLM_API_KEY" in response.json()["detail"]


async def test_chat_grounds_the_answer_in_live_data(
    client: httpx.AsyncClient,
    stub_llm: _StubLLM,
) -> None:
    response = await client.post(
        "/api/v1/chat",
        json={"question": "How is gold trending?", "symbol": "XAUUSD", "timeframe": "H1"},
    )
    assert response.status_code == 200
    body = response.json()

    assert body["answer"]
    assert body["model"] == "stub-chat-model"
    assert body["symbol"] == "XAUUSD"
    assert body["timeframe"] == "H1"
    assert body["data_status"] == {"quote": "ok", "ohlc": "ok", "news": "ok"}

    # The snapshot is the evidence the answer was drawn from.
    assert body["snapshot"]["quote"]["last"] == 2640.2
    assert body["snapshot"]["technicals"]["last_close"] == 2661.0
    assert body["snapshot"]["news"][0]["title"].startswith("Gold steadies")

    # The live figures, not the client's own claim about them, reached the model.
    prompt = stub_llm.prompts[0]
    assert "2640.2" in prompt
    assert "Gold steadies as traders await inflation print" in prompt
    assert "close_above_sma20" in prompt
    assert "How is gold trending?" in prompt


async def test_chat_sends_a_grounding_system_prompt(
    client: httpx.AsyncClient,
    stub_llm: _StubLLM,
) -> None:
    await client.post("/api/v1/chat", json={"question": "Any risk?"})
    system = stub_llm.systems[0]
    assert system is not None
    assert "ONLY the figures and headlines supplied" in system
    assert "Never invent" in system


async def test_chat_includes_recent_history(
    client: httpx.AsyncClient,
    stub_llm: _StubLLM,
) -> None:
    await client.post(
        "/api/v1/chat",
        json={
            "question": "And the higher timeframe?",
            "history": [
                {"role": "user", "content": "Where is gold?"},
                {"role": "assistant", "content": "It is trending up on H1."},
            ],
        },
    )
    prompt = stub_llm.prompts[0]
    assert "user: Where is gold?" in prompt
    assert "assistant: It is trending up on H1." in prompt


async def test_chat_reports_a_failed_source_without_failing(
    client: httpx.AsyncClient,
    stub_llm: _StubLLM,
    configured_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A dead news feed degrades that section and is disclosed to the model."""

    async def _boom(**_: Any) -> list[NewsArticle]:
        raise RuntimeError("news provider down")

    monkeypatch.setattr(
        configured_app.state.pipeline.client, "get_news", _boom, raising=False
    )

    response = await client.post("/api/v1/chat", json={"question": "Any news?"})
    assert response.status_code == 200
    body = response.json()
    assert body["data_status"]["news"].startswith("unavailable")
    assert body["data_status"]["quote"] == "ok"
    assert body["snapshot"]["news"] == []

    prompt = stub_llm.prompts[0]
    assert "failed to load: news" in prompt
    assert "Do not fill those gaps" in prompt


async def test_chat_rejects_an_empty_question(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/v1/chat", json={"question": ""})
    assert response.status_code == 422
