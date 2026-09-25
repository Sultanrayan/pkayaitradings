"""Tests for CORS configuration and the live-tick WebSocket endpoint."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, ClassVar

import httpx

from orchestrator import main as orchestrator_main
from shared.schemas.enums import MarketState
from shared.schemas.market import Tick
from shared.utils.time import utcnow


def _tick(symbol: str = "XAUUSD", mid: float = 2650.0) -> Tick:
    return Tick(
        symbol=symbol,
        bid=mid - 0.2,
        ask=mid + 0.2,
        mid=mid,
        spread=0.4,
        timestamp=utcnow(),
        marketState=MarketState.OPEN.value,
    )


class _FakeWebSocket:
    def __init__(self) -> None:
        self.accepted = False
        self.closed = False
        self.sent: list[dict[str, Any]] = []

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, data: dict[str, Any]) -> None:
        self.sent.append(data)

    async def close(self) -> None:
        self.closed = True


class _FakeFeed:
    """Minimal BiquoteTickFeed stand-in for the WebSocket endpoint."""

    instances: ClassVar[list[_FakeFeed]] = []
    fail_start = False

    def __init__(self, symbols: Any = ()) -> None:
        self.symbols = list(symbols)
        self.started = False
        self.stopped = False
        _FakeFeed.instances.append(self)

    async def start(self) -> None:
        if _FakeFeed.fail_start:
            raise RuntimeError("feed down")
        self.started = True

    async def stop(self) -> None:
        self.stopped = True

    async def snapshot(self) -> dict[str, Tick]:
        return {symbol: _tick(symbol) for symbol in self.symbols}

    async def stream(self) -> AsyncIterator[Tick]:
        for symbol in self.symbols:
            yield _tick(symbol, mid=2700.0)


async def test_ws_ticks_sends_snapshot_then_streams(monkeypatch: Any) -> None:
    _FakeFeed.instances.clear()
    _FakeFeed.fail_start = False
    monkeypatch.setattr(orchestrator_main, "BiquoteTickFeed", _FakeFeed)

    websocket = _FakeWebSocket()
    await orchestrator_main.stream_ticks(websocket, symbols="XAUUSD")  # type: ignore[arg-type]

    assert websocket.accepted
    assert websocket.sent[0]["type"] == "snapshot"
    assert "XAUUSD" in websocket.sent[0]["ticks"]
    assert websocket.sent[1]["type"] == "tick"
    assert websocket.sent[1]["tick"]["symbol"] == "XAUUSD"

    feed = _FakeFeed.instances[0]
    assert feed.started and feed.stopped


async def test_ws_ticks_defaults_to_configured_symbols(monkeypatch: Any) -> None:
    _FakeFeed.instances.clear()
    _FakeFeed.fail_start = False
    monkeypatch.setattr(orchestrator_main, "BiquoteTickFeed", _FakeFeed)

    websocket = _FakeWebSocket()
    await orchestrator_main.stream_ticks(websocket, symbols="")  # type: ignore[arg-type]
    assert websocket.sent[0]["symbols"]


async def test_ws_ticks_reports_errors(monkeypatch: Any) -> None:
    _FakeFeed.instances.clear()
    _FakeFeed.fail_start = True
    monkeypatch.setattr(orchestrator_main, "BiquoteTickFeed", _FakeFeed)

    websocket = _FakeWebSocket()
    await orchestrator_main.stream_ticks(websocket, symbols="XAUUSD")  # type: ignore[arg-type]

    assert websocket.sent[0]["type"] == "error"
    assert websocket.closed
    assert _FakeFeed.instances[0].stopped


async def test_cors_allows_configured_origin() -> None:
    transport = httpx.ASGITransport(app=orchestrator_main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health", headers={"Origin": "http://localhost:3000"})
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"


async def test_cors_preflight() -> None:
    transport = httpx.ASGITransport(app=orchestrator_main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.options(
            "/api/v1/analyze/XAUUSD",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
            },
        )
    assert response.status_code in {200, 204}
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"
