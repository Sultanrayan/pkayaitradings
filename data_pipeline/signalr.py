"""A minimal, dependency-light SignalR (JSON protocol) client.

Implements just enough of the ASP.NET Core SignalR JSON hub protocol to consume
biquote's tick hub at ``wss://biquote.io/hubs/tick``:

* HTTP negotiate handshake (with a direct-connect fallback),
* the ``\\x1e`` record-separated JSON framing,
* server→client invocations dispatched to registered handlers,
* client→server invocations with optional completion results,
* ping/pong keep-alive and automatic reconnection with exponential backoff.

Reference: https://github.com/dotnet/aspnetcore/blob/main/src/SignalR/docs/specs/HubProtocol.md
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import random
import uuid
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import urlparse, urlunparse

import httpx
import websockets
from websockets.asyncio.client import ClientConnection

from data_pipeline.errors import BiquoteError
from shared.logging import get_logger

_logger = get_logger(__name__)

_RECORD_SEPARATOR = "\x1e"

_INVOCATION = 1
_STREAM_ITEM = 2
_COMPLETION = 3
_PING = 6
_CLOSE = 7

Handler = Callable[[list[Any]], Any]


class SignalRClient:
    """A reconnecting SignalR JSON-protocol client.

    Args:
        hub_url: Absolute hub URL, e.g. ``https://biquote.io/hubs/tick``.
        timeout: Negotiate/connect timeout in seconds.
    """

    def __init__(self, hub_url: str, *, timeout: float = 10.0) -> None:
        self._hub_url = hub_url
        self._timeout = timeout
        self._handlers: dict[str, list[Handler]] = {}
        self._connect_hooks: list[Callable[[], Awaitable[None]]] = []
        self._pending: dict[str, asyncio.Future[Any]] = {}
        self._connection: ClientConnection | None = None
        self._recv_task: asyncio.Task[None] | None = None
        self._reconnect_task: asyncio.Task[None] | None = None
        self._closing = False
        self._handshake_done = asyncio.Event()

    # ------------------------------------------------------------------ #
    # Handler registration
    # ------------------------------------------------------------------ #
    def on(self, target: str, handler: Handler) -> None:
        """Register ``handler`` for server→client invocations named ``target``."""
        self._handlers.setdefault(target, []).append(handler)

    def on_connected(self, hook: Callable[[], Awaitable[None]]) -> None:
        """Register an async hook run after every successful (re)connect."""
        self._connect_hooks.append(hook)

    @property
    def is_connected(self) -> bool:
        """Whether the socket is open and the handshake has completed."""
        return self._connection is not None and self._handshake_done.is_set()

    # ------------------------------------------------------------------ #
    # Connection lifecycle
    # ------------------------------------------------------------------ #
    async def connect(self) -> None:
        """Negotiate and open the WebSocket, completing the handshake."""
        self._closing = False
        url = await self._negotiate()
        _logger.info("signalr.connecting", url=url)
        self._connection = await websockets.connect(
            url,
            open_timeout=self._timeout,
            ping_interval=None,
            max_size=2**22,
        )
        await self._perform_handshake()
        self._recv_task = asyncio.create_task(self._receive_loop(), name="signalr-recv")
        for hook in self._connect_hooks:
            await hook()

    async def _negotiate(self) -> str:
        """Resolve the WebSocket URL, falling back to direct connect."""
        parsed = urlparse(self._hub_url)
        scheme = "wss" if parsed.scheme == "https" else "ws"
        base = urlunparse((scheme, parsed.netloc, parsed.path, "", "", ""))
        negotiate_url = f"{self._hub_url.rstrip('/')}/negotiate?negotiateVersion=1"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(negotiate_url)
                response.raise_for_status()
                payload = response.json()
            token = payload.get("connectionToken") or payload.get("connectionId")
            if token:
                return f"{base}?id={token}"
        except (httpx.HTTPError, ValueError) as exc:
            _logger.warning("signalr.negotiate_failed", error=repr(exc))
        return base

    async def _perform_handshake(self) -> None:
        assert self._connection is not None
        self._handshake_done.clear()
        await self._connection.send(
            json.dumps({"protocol": "json", "version": 1}) + _RECORD_SEPARATOR
        )
        raw = await asyncio.wait_for(self._connection.recv(), timeout=self._timeout)
        text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        if text.strip(_RECORD_SEPARATOR).strip() != "{}":
            raise BiquoteError(f"Unexpected SignalR handshake response: {text!r}")
        self._handshake_done.set()
        _logger.info("signalr.connected")

    async def close(self) -> None:
        """Gracefully close the connection and cancel background tasks."""
        self._closing = True
        for task in (self._reconnect_task, self._recv_task):
            if task is not None:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
        self._reconnect_task = None
        self._recv_task = None
        if self._connection is not None:
            with contextlib.suppress(Exception):
                await self._connection.close()
            self._connection = None
        self._fail_pending(BiquoteError("SignalR connection closed"))

    async def __aenter__(self) -> SignalRClient:
        await self.connect()
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.close()

    # ------------------------------------------------------------------ #
    # Sending
    # ------------------------------------------------------------------ #
    async def send(self, target: str, *args: Any) -> None:
        """Send a fire-and-forget invocation to the hub."""
        await self._ensure_connected()
        await self._send_message({"type": _INVOCATION, "target": target, "arguments": list(args)})

    async def invoke(self, target: str, *args: Any) -> Any:
        """Invoke a hub method and await its completion result."""
        await self._ensure_connected()
        invocation_id = uuid.uuid4().hex
        loop = asyncio.get_running_loop()
        future: asyncio.Future[Any] = loop.create_future()
        self._pending[invocation_id] = future
        await self._send_message(
            {
                "type": _INVOCATION,
                "invocationId": invocation_id,
                "target": target,
                "arguments": list(args),
            }
        )
        try:
            return await asyncio.wait_for(future, timeout=self._timeout)
        finally:
            self._pending.pop(invocation_id, None)

    async def _ensure_connected(self) -> None:
        if self._connection is None:
            await self.connect()
        await self._handshake_done.wait()

    async def _send_message(self, message: dict[str, Any]) -> None:
        assert self._connection is not None
        await self._connection.send(json.dumps(message) + _RECORD_SEPARATOR)

    # ------------------------------------------------------------------ #
    # Receiving
    # ------------------------------------------------------------------ #
    async def _receive_loop(self) -> None:
        assert self._connection is not None
        try:
            async for raw in self._connection:
                text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
                for frame in _split_frames(text):
                    await self._handle_frame(frame)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if not self._closing:
                _logger.warning("signalr.receive_error", error=repr(exc))
                self._reconnect_task = asyncio.create_task(self._reconnect())
        finally:
            self._fail_pending(BiquoteError("SignalR receive loop ended"))

    async def _handle_frame(self, frame: str) -> None:
        if not frame:
            return
        try:
            message = json.loads(frame)
        except ValueError:
            _logger.debug("signalr.unparseable_frame", frame=frame[:200])
            return

        message_type = message.get("type")
        if message_type == _INVOCATION:
            await self._dispatch(message)
        elif message_type == _COMPLETION:
            self._resolve_pending(message)
        elif message_type == _PING:
            await self._send_message({"type": _PING})
        elif message_type == _CLOSE:
            _logger.warning("signalr.server_close", error=message.get("error"))

    async def _dispatch(self, message: dict[str, Any]) -> None:
        target = message.get("target", "")
        arguments = message.get("arguments", [])
        for handler in self._handlers.get(target, []):
            try:
                result = handler(arguments)
                if isinstance(result, Awaitable):
                    await result
            except Exception:
                _logger.exception("signalr.handler_error", target=target)

    def _resolve_pending(self, message: dict[str, Any]) -> None:
        invocation_id = message.get("invocationId")
        future = self._pending.get(invocation_id) if invocation_id else None
        if future is None or future.done():
            return
        error = message.get("error")
        if error:
            future.set_exception(BiquoteError(str(error)))
        else:
            future.set_result(message.get("result"))

    def _fail_pending(self, exc: Exception) -> None:
        for future in self._pending.values():
            if not future.done():
                future.set_exception(exc)

    async def _reconnect(self) -> None:
        delay = 1.0
        while not self._closing:
            try:
                await self.close_connection_only()
                await asyncio.sleep(delay)
                await self.connect()
                for target in self._handlers:
                    _logger.info("signalr.reconnected", target=target)
                return
            except Exception as exc:
                _logger.warning("signalr.reconnect_failed", error=repr(exc), delay=delay)
                delay = min(delay * 2, 30.0) + random.uniform(0, 1)

    async def close_connection_only(self) -> None:
        """Close the socket without cancelling the receive loop task."""
        if self._connection is not None:
            with contextlib.suppress(Exception):
                await self._connection.close()
            self._connection = None


def _split_frames(text: str) -> list[str]:
    """Split a record-separated SignalR payload into non-empty frames."""
    return [frame for frame in text.split(_RECORD_SEPARATOR) if frame]
