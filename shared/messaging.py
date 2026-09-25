"""Message-bus abstractions used by the agents and orchestrator.

Two implementations are provided:

* :class:`RedisMessageBus` — production pub/sub over Redis.
* :class:`InMemoryMessageBus` — dependency-free bus for tests and single-process
  runs.

Channels follow the ``signals.<agent>`` convention and may be subscribed to with
``fnmatch`` glob patterns, e.g. ``signals.*``.
"""

from __future__ import annotations

import asyncio
import contextlib
import fnmatch
from collections.abc import AsyncIterator
from typing import Any, Protocol, runtime_checkable

from shared.logging import get_logger
from shared.schemas.messages import AgentMessage

_logger = get_logger(__name__)


@runtime_checkable
class MessageBus(Protocol):
    """Publish/subscribe transport for :class:`AgentMessage` envelopes."""

    async def publish(self, channel: str, message: AgentMessage) -> None:
        """Publish ``message`` to ``channel``."""

    def subscribe(self, pattern: str) -> AsyncIterator[AgentMessage]:
        """Yield messages published to channels matching ``pattern``."""

    async def close(self) -> None:
        """Release any underlying resources."""


class InMemoryMessageBus:
    """A single-process pub/sub bus backed by asyncio queues."""

    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[AgentMessage]]] = {}
        self._closed = False

    async def publish(self, channel: str, message: AgentMessage) -> None:
        """Fan the message out to every pattern that matches ``channel``."""
        if self._closed:
            raise RuntimeError("Message bus is closed")
        for pattern, queues in list(self._subscribers.items()):
            if fnmatch.fnmatchcase(channel, pattern):
                for queue in list(queues):
                    with contextlib.suppress(asyncio.QueueFull):
                        queue.put_nowait(message)

    async def subscribe(self, pattern: str) -> AsyncIterator[AgentMessage]:
        """Yield messages matching ``pattern`` until the bus is closed."""
        queue: asyncio.Queue[AgentMessage] = asyncio.Queue(maxsize=10_000)
        self._subscribers.setdefault(pattern, set()).add(queue)
        try:
            while not self._closed:
                try:
                    yield await asyncio.wait_for(queue.get(), timeout=1.0)
                except TimeoutError:
                    continue
        finally:
            self._subscribers.get(pattern, set()).discard(queue)

    async def close(self) -> None:
        """Mark the bus closed; active subscriptions wind down."""
        self._closed = True


class RedisMessageBus:
    """Redis pub/sub transport.

    Args:
        url: Redis connection URL, e.g. ``redis://localhost:6379/0``.
    """

    def __init__(self, url: str) -> None:
        import redis.asyncio as aioredis

        self._url = url
        self._redis: Any = aioredis.from_url(url, decode_responses=True)

    async def ping(self) -> bool:
        """Return ``True`` if Redis responds to a ping."""
        return bool(await self._redis.ping())

    async def publish(self, channel: str, message: AgentMessage) -> None:
        """Publish the message as JSON on ``channel``."""
        await self._redis.publish(channel, message.model_dump_json())

    async def subscribe(self, pattern: str) -> AsyncIterator[AgentMessage]:
        """Yield messages matching the Redis glob ``pattern``."""
        pubsub = self._redis.pubsub()
        await pubsub.psubscribe(pattern)
        try:
            async for raw in pubsub.listen():
                if raw.get("type") not in {"message", "pmessage"}:
                    continue
                data = raw.get("data")
                if not isinstance(data, str):
                    continue
                try:
                    yield AgentMessage.model_validate_json(data)
                except ValueError:
                    _logger.warning("bus.malformed_message", channel=raw.get("channel"))
        finally:
            with contextlib.suppress(Exception):
                await pubsub.punsubscribe(pattern)
                await pubsub.aclose()

    async def close(self) -> None:
        """Close the Redis connection pool."""
        with contextlib.suppress(Exception):
            await self._redis.aclose()


async def create_message_bus(settings: Any | None = None) -> MessageBus:
    """Build a Redis bus if reachable, otherwise fall back to in-memory.

    The fallback keeps local development and tests working without Redis.
    """
    from shared.config import get_settings

    settings = settings or get_settings()
    try:
        bus = RedisMessageBus(settings.redis_url)
        await bus.ping()
        return bus
    except Exception as exc:
        _logger.warning("bus.redis_unavailable", error=repr(exc))
        return InMemoryMessageBus()
