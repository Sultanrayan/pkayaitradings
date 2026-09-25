"""Tests for the SignalR client and biquote tick feeds."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock

import httpx
import pytest
import respx

from data_pipeline import signalr as signalr_module
from data_pipeline.biquote_feed import BiquoteTickFeed, PollingTickFeed
from data_pipeline.signalr import _RECORD_SEPARATOR, SignalRClient
from shared.schemas.market import Tick
from shared.utils.time import utcnow

BASE = "https://biquote.io"
HUB = f"{BASE}/hubs/tick"


class _FakeConnection:
    def __init__(self, incoming: list[str] | None = None) -> None:
        self.sent: list[str] = []
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        for item in incoming or []:
            self._queue.put_nowait(item)
        self.closed = False

    async def send(self, data: str) -> None:
        self.sent.append(data)

    async def recv(self) -> str:
        return await self._queue.get()

    def __aiter__(self) -> _FakeConnection:
        return self

    async def __anext__(self) -> str:
        try:
            return await asyncio.wait_for(self._queue.get(), timeout=0.05)
        except TimeoutError as exc:
            raise StopAsyncIteration from exc

    async def close(self) -> None:
        self.closed = True


def _tick_payload(symbol: str = "XAUUSD", mid: float = 2650.0) -> dict[str, object]:
    return {
        "symbol": symbol,
        "bid": mid - 0.1,
        "ask": mid + 0.1,
        "mid": mid,
        "spread": 0.2,
        "timestamp": utcnow().isoformat(),
        "marketState": "open",
        "stale": False,
        "quoteAgeSeconds": 0,
    }


@respx.mock
async def test_negotiate_uses_connection_token() -> None:
    respx.post(f"{HUB}/negotiate").mock(
        return_value=httpx.Response(200, json={"connectionToken": "abc123"})
    )
    client = SignalRClient(HUB)
    url = await client._negotiate()
    assert url.endswith("?id=abc123")


@respx.mock
async def test_negotiate_falls_back_to_direct() -> None:
    respx.post(f"{HUB}/negotiate").mock(side_effect=httpx.ConnectError("nope"))
    client = SignalRClient(HUB)
    url = await client._negotiate()
    assert url == "wss://biquote.io/hubs/tick"


async def test_connect_performs_handshake_and_dispatches(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeConnection(incoming=[f"{{}}{_RECORD_SEPARATOR}"])
    monkeypatch.setattr(signalr_module.websockets, "connect", AsyncMock(return_value=fake))
    client = SignalRClient(HUB)
    monkeypatch.setattr(client, "_negotiate", AsyncMock(return_value="ws://x/hub"))

    received: list[list[object]] = []
    client.on("ReceiveTick", received.append)
    await client.connect()
    assert client.is_connected

    await fake._queue.put(
        json.dumps({"type": 1, "target": "ReceiveTick", "arguments": [{"symbol": "XAUUSD"}]})
        + _RECORD_SEPARATOR
    )
    await asyncio.sleep(0.02)
    assert received
    await client.close()
    assert fake.closed


async def test_handshake_failure_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeConnection(incoming=[f"garbage{_RECORD_SEPARATOR}"])
    monkeypatch.setattr(signalr_module.websockets, "connect", AsyncMock(return_value=fake))
    client = SignalRClient(HUB)
    monkeypatch.setattr(client, "_negotiate", AsyncMock(return_value="ws://x/hub"))
    with pytest.raises(Exception, match="handshake"):
        await client.connect()


async def test_send_and_ping_use_connection() -> None:
    client = SignalRClient(HUB)
    fake = _FakeConnection()
    client._connection = fake  # type: ignore[assignment]
    client._handshake_done.set()

    await client.send("Subscribe", ["XAUUSD"])
    await client._handle_frame(json.dumps({"type": 6}))

    messages = [json.loads(message.rstrip(_RECORD_SEPARATOR)) for message in fake.sent]
    assert messages[0]["target"] == "Subscribe"
    assert messages[-1] == {"type": 6}


async def test_invoke_resolves_completion() -> None:
    client = SignalRClient(HUB)
    fake = _FakeConnection()
    client._connection = fake  # type: ignore[assignment]
    client._handshake_done.set()

    task = asyncio.create_task(client.invoke("GetLatestTick", "XAUUSD"))
    await asyncio.sleep(0)
    sent = json.loads(fake.sent[-1].rstrip(_RECORD_SEPARATOR))
    client._resolve_pending(
        {"type": 3, "invocationId": sent["invocationId"], "result": {"mid": 1.23}}
    )
    assert await task == {"mid": 1.23}


async def test_invoke_propagates_error() -> None:
    client = SignalRClient(HUB)
    fake = _FakeConnection()
    client._connection = fake  # type: ignore[assignment]
    client._handshake_done.set()

    task = asyncio.create_task(client.invoke("GetLatestTick", "XAUUSD"))
    await asyncio.sleep(0)
    sent = json.loads(fake.sent[-1].rstrip(_RECORD_SEPARATOR))
    client._resolve_pending({"type": 3, "invocationId": sent["invocationId"], "error": "boom"})
    with pytest.raises(Exception, match="boom"):
        await task


async def test_reconnect_reestablishes(monkeypatch: pytest.MonkeyPatch) -> None:
    client = SignalRClient(HUB)
    monkeypatch.setattr(client, "close_connection_only", AsyncMock(return_value=None))
    monkeypatch.setattr(client, "connect", AsyncMock(return_value=None))
    await client._reconnect()


class _FakeHub:
    def __init__(self) -> None:
        self.sent: list[tuple[str, tuple[object, ...]]] = []
        self.connected = False
        self.hook = None

    def on(self, *_: object) -> None:
        return None

    def on_connected(self, hook: object) -> None:
        self.hook = hook

    async def connect(self) -> None:
        self.connected = True

    async def send(self, target: str, *args: object) -> None:
        self.sent.append((target, args))

    async def close(self) -> None:
        self.connected = False

    @property
    def is_connected(self) -> bool:
        return self.connected

    async def invoke(self, target: str, *args: object) -> dict[str, object]:
        return _tick_payload()


class _FakeClient:
    def __init__(self) -> None:
        self.closed = False
        self.raise_on_latest = False

    async def get_latest(self, symbols: list[str], **_: object) -> dict[str, Tick]:
        if self.raise_on_latest:
            raise RuntimeError("boom")
        return {symbol: Tick.model_validate(_tick_payload(symbol)) for symbol in symbols}

    async def close(self) -> None:
        self.closed = True


async def test_biquote_feed_lifecycle() -> None:
    client = _FakeClient()
    feed = BiquoteTickFeed(["XAUUSD"], client=client)  # type: ignore[arg-type]
    hub = _FakeHub()
    feed._hub = hub  # type: ignore[assignment]

    await feed.start()
    assert hub.connected
    assert hub.sent[0][0] == "Subscribe"

    await feed.subscribe(["BTCUSD"])
    assert any(target == "Subscribe" for target, _ in hub.sent)
    await feed.unsubscribe(["XAUUSD"])
    assert any(target == "Unsubscribe" for target, _ in hub.sent)

    tick = await feed.get_latest_tick("XAUUSD")
    assert tick.symbol == "XAUUSD"

    snapshot = await feed.snapshot()
    assert "XAUUSD" in snapshot or "BTCUSD" in snapshot

    await feed._resubscribe()
    await feed.stop()
    assert client.closed


async def test_biquote_feed_stream_yields_queued_tick() -> None:
    feed = BiquoteTickFeed(["XAUUSD"], client=_FakeClient())  # type: ignore[arg-type]
    feed._running = True
    feed._on_tick([_tick_payload()])
    stream = feed.stream()
    tick = await asyncio.wait_for(anext(stream), timeout=1.0)
    assert tick.symbol == "XAUUSD"
    feed._running = False


async def test_polling_feed_handles_errors_and_stops() -> None:
    client = _FakeClient()
    client.raise_on_latest = True
    feed = PollingTickFeed(["XAUUSD"], interval_seconds=0.02, client=client)  # type: ignore[arg-type]
    await feed.start()
    await asyncio.sleep(0.06)  # exercise the error-handling branch of the poll loop

    client.raise_on_latest = False
    await feed.subscribe(["BTCUSD"])
    await feed.unsubscribe(["XAUUSD"])
    snapshot = await feed.snapshot()
    assert set(snapshot) == {"BTCUSD"}

    await feed.stop()
    assert client.closed
