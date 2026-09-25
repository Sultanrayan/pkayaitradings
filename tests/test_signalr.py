"""Tests for the SignalR JSON-protocol client internals."""

from __future__ import annotations

import asyncio
import json

import pytest

from data_pipeline.signalr import _RECORD_SEPARATOR, SignalRClient, _split_frames


def test_split_frames_filters_empty_segments() -> None:
    payload = f'{{"a":1}}{_RECORD_SEPARATOR}{_RECORD_SEPARATOR}{{"b":2}}{_RECORD_SEPARATOR}'
    assert _split_frames(payload) == ['{"a":1}', '{"b":2}']


async def test_handle_frame_dispatches_to_registered_handler() -> None:
    client = SignalRClient("https://example.test/hubs/tick")
    received: list[list[object]] = []
    client.on("ReceiveTick", received.append)

    await client._handle_frame(
        json.dumps({"type": 1, "target": "ReceiveTick", "arguments": [{"symbol": "XAUUSD"}]})
    )

    assert received == [[{"symbol": "XAUUSD"}]]


async def test_handle_frame_resolves_pending_invocation() -> None:
    client = SignalRClient("https://example.test/hubs/tick")
    loop = asyncio.get_running_loop()
    future: asyncio.Future[object] = loop.create_future()
    client._pending["abc"] = future

    await client._handle_frame(
        json.dumps({"type": 3, "invocationId": "abc", "result": {"mid": 1.23}})
    )

    assert future.result() == {"mid": 1.23}


async def test_handle_frame_propagates_invocation_error() -> None:
    client = SignalRClient("https://example.test/hubs/tick")
    loop = asyncio.get_running_loop()
    future: asyncio.Future[object] = loop.create_future()
    client._pending["abc"] = future

    await client._handle_frame(json.dumps({"type": 3, "invocationId": "abc", "error": "boom"}))

    with pytest.raises(Exception, match="boom"):
        future.result()


async def test_handler_exception_does_not_propagate() -> None:
    client = SignalRClient("https://example.test/hubs/tick")

    def bad_handler(_: list[object]) -> None:
        raise RuntimeError("handler failed")

    client.on("ReceiveTick", bad_handler)
    await client._handle_frame(json.dumps({"type": 1, "target": "ReceiveTick", "arguments": [{}]}))


async def test_unparseable_frame_is_ignored() -> None:
    client = SignalRClient("https://example.test/hubs/tick")
    await client._handle_frame("not-json")
