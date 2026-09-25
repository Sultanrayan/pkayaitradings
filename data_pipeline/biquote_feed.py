"""Real-time tick feeds for biquote.

The primary feed consumes biquote's SignalR hub, which pushes every tick over a
single unmetered connection. A polling feed is provided as a fallback for
environments where WebSockets are unavailable; it uses the batch ``/api/latest``
endpoint so it stays well within the rate limit.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator, Iterable
from typing import Any, Protocol

from data_pipeline.biquote_client import BiquoteClient
from data_pipeline.signalr import SignalRClient
from shared.config import Settings, get_settings
from shared.logging import get_logger
from shared.schemas.market import Tick

_logger = get_logger(__name__)

_DEFAULT_HUB = "https://biquote.io/hubs/tick"


class TickFeed(Protocol):
    """Common interface for real-time tick sources."""

    async def start(self) -> None:
        """Begin producing ticks."""

    async def stop(self) -> None:
        """Stop producing ticks and release resources."""

    def stream(self) -> AsyncIterator[Tick]:
        """Yield ticks as they arrive."""

    async def snapshot(self) -> dict[str, Tick]:
        """Return the latest known tick per subscribed symbol."""


class BiquoteTickFeed:
    """SignalR-backed live tick feed with a REST snapshot seed.

    Args:
        symbols: Symbols to subscribe to on start.
        settings: Optional settings override.
        hub_url: Optional hub URL override (useful for testing).
        client: Optional REST client used for the initial snapshot.
    """

    def __init__(
        self,
        symbols: Iterable[str] = (),
        *,
        settings: Settings | None = None,
        hub_url: str | None = None,
        client: BiquoteClient | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._symbols: set[str] = {symbol.upper() for symbol in symbols}
        self._client = client or BiquoteClient(self._settings)
        self._hub = SignalRClient(
            hub_url or _DEFAULT_HUB, timeout=self._settings.biquote_timeout_seconds
        )
        self._queue: asyncio.Queue[Tick] = asyncio.Queue(maxsize=10_000)
        self._states: dict[str, dict[str, Any]] = {}
        self._running = False

        self._hub.on("ReceiveTick", self._on_tick)
        self._hub.on("ReceiveSubscriptionState", self._on_subscription_state)
        self._hub.on_connected(self._resubscribe)

    @property
    def subscription_states(self) -> dict[str, dict[str, Any]]:
        """Last known subscription state per symbol, as reported by the hub."""
        return dict(self._states)

    async def start(self) -> None:
        """Seed from REST, connect to the hub and subscribe."""
        if self._running:
            return
        self._running = True
        await self._hub.connect()
        if self._symbols:
            await self._hub.send("Subscribe", sorted(self._symbols))

    async def stop(self) -> None:
        """Disconnect and close the REST client."""
        self._running = False
        await self._hub.close()
        await self._client.close()

    async def _resubscribe(self) -> None:
        if self._symbols:
            _logger.info("biquote_feed.resubscribe", symbols=sorted(self._symbols))
            await self._hub.send("Subscribe", sorted(self._symbols))

    async def subscribe(self, symbols: Iterable[str]) -> None:
        """Add symbols to the subscription and notify the hub if connected."""
        new_symbols = {symbol.upper() for symbol in symbols} - self._symbols
        if not new_symbols:
            return
        self._symbols |= new_symbols
        if self._hub.is_connected:
            await self._hub.send("Subscribe", sorted(new_symbols))

    async def unsubscribe(self, symbols: Iterable[str]) -> None:
        """Remove symbols from the subscription and notify the hub if connected."""
        removed = {symbol.upper() for symbol in symbols} & self._symbols
        if not removed:
            return
        self._symbols -= removed
        if self._hub.is_connected:
            await self._hub.send("Unsubscribe", sorted(removed))

    async def get_latest_tick(self, symbol: str) -> Tick:
        """Request a single tick through the hub."""
        payload = await self._hub.invoke("GetLatestTick", symbol.upper())
        return Tick.model_validate(payload)

    async def snapshot(self) -> dict[str, Tick]:
        """Fetch a REST snapshot for all subscribed symbols in one request."""
        if not self._symbols:
            return {}
        return await self._client.get_latest(sorted(self._symbols))

    async def stream(self) -> AsyncIterator[Tick]:
        """Yield ticks pushed by the hub until :meth:`stop` is called."""
        while self._running or not self._queue.empty():
            try:
                yield await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except TimeoutError:
                continue

    def _on_tick(self, arguments: list[Any]) -> None:
        if not arguments:
            return
        try:
            tick = Tick.model_validate(arguments[0])
        except Exception:
            _logger.warning("biquote_feed.bad_tick", payload=arguments[0])
            return
        with contextlib.suppress(asyncio.QueueFull):
            self._queue.put_nowait(tick)

    def _on_subscription_state(self, arguments: list[Any]) -> None:
        if not arguments:
            return
        states = arguments[0]
        if isinstance(states, list):
            for state in states:
                if isinstance(state, dict) and "symbol" in state:
                    self._states[state["symbol"]] = state
                    if state.get("state") == "unknown":
                        _logger.warning("biquote_feed.unknown_symbol", symbol=state["symbol"])


class PollingTickFeed:
    """REST polling fallback that batches all symbols into one request.

    Args:
        symbols: Symbols to poll.
        interval_seconds: Seconds between polls. Defaults to 2.0.
        settings: Optional settings override.
        client: Optional REST client.
    """

    def __init__(
        self,
        symbols: Iterable[str] = (),
        *,
        interval_seconds: float = 2.0,
        settings: Settings | None = None,
        client: BiquoteClient | None = None,
    ) -> None:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
        self._settings = settings or get_settings()
        self._symbols: set[str] = {symbol.upper() for symbol in symbols}
        self._interval = interval_seconds
        self._client = client or BiquoteClient(self._settings)
        self._queue: asyncio.Queue[Tick] = asyncio.Queue(maxsize=10_000)
        self._task: asyncio.Task[None] | None = None
        self._running = False

    async def start(self) -> None:
        """Start the polling loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._poll_loop(), name="biquote-poll")

    async def stop(self) -> None:
        """Stop the polling loop and close the REST client."""
        self._running = False
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        await self._client.close()

    async def subscribe(self, symbols: Iterable[str]) -> None:
        """Add symbols to the poll set."""
        self._symbols |= {symbol.upper() for symbol in symbols}

    async def unsubscribe(self, symbols: Iterable[str]) -> None:
        """Remove symbols from the poll set."""
        self._symbols -= {symbol.upper() for symbol in symbols}

    async def snapshot(self) -> dict[str, Tick]:
        """Return a batch snapshot of all subscribed symbols."""
        if not self._symbols:
            return {}
        return await self._client.get_latest(sorted(self._symbols))

    async def _poll_loop(self) -> None:
        while self._running:
            try:
                ticks = await self.snapshot()
                for tick in ticks.values():
                    with contextlib.suppress(asyncio.QueueFull):
                        self._queue.put_nowait(tick)
            except Exception as exc:
                _logger.warning("biquote_poll.error", error=repr(exc))
            await asyncio.sleep(self._interval)

    async def stream(self) -> AsyncIterator[Tick]:
        """Yield ticks from the polling queue until :meth:`stop` is called."""
        while self._running or not self._queue.empty():
            try:
                yield await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except TimeoutError:
                continue
