"""Tests for the message bus and base agent publishing."""

from __future__ import annotations

import asyncio

import pytest

from agents.base_agent import BaseAgent
from shared.messaging import InMemoryMessageBus
from shared.schemas.enums import AgentName, Direction, Timeframe
from shared.schemas.messages import AgentMessage
from shared.schemas.signals import TechnicalSignal


class _StubAgent(BaseAgent):
    name = AgentName.TECHNICAL_ANALYST

    async def run(self) -> TechnicalSignal:  # type: ignore[override]
        signal = TechnicalSignal(
            symbol="XAUUSD",
            timeframe=Timeframe.H1,
            signal=Direction.BULLISH,
            confidence=0.8,
        )
        await self.publish(signal, kind="technical_signal")
        return signal


async def test_in_memory_bus_routes_by_glob_pattern() -> None:
    bus = InMemoryMessageBus()
    message = AgentMessage(
        source=AgentName.TECHNICAL_ANALYST, kind="technical_signal", payload={"a": 1}
    )

    received: list[AgentMessage] = []

    async def consume() -> None:
        async for item in bus.subscribe("signals.*"):
            received.append(item)
            break

    task = asyncio.create_task(consume())
    await asyncio.sleep(0)  # let the subscriber register
    await bus.publish("signals.technical_analyst", message)
    await asyncio.wait_for(task, timeout=2.0)

    assert received == [message]
    await bus.close()


async def test_bus_ignores_non_matching_channels() -> None:
    bus = InMemoryMessageBus()
    message = AgentMessage(source=AgentName.NEWS_MONITOR, kind="news_signal", payload={})

    stream = bus.subscribe("signals.technical_analyst")
    task = asyncio.create_task(anext(stream))
    await asyncio.sleep(0)
    await bus.publish("signals.news_monitor", message)
    await asyncio.sleep(0.05)

    assert not task.done()
    task.cancel()
    await bus.close()


async def test_base_agent_publishes_typed_payload() -> None:
    bus = InMemoryMessageBus()
    agent = _StubAgent(bus=bus)

    received: list[AgentMessage] = []

    async def consume() -> None:
        async for item in bus.subscribe("signals.technical_analyst"):
            received.append(item)
            break

    task = asyncio.create_task(consume())
    await asyncio.sleep(0)
    await agent.run()
    await asyncio.wait_for(task, timeout=2.0)

    assert received[0].kind == "technical_signal"
    assert received[0].payload["signal"] == "BULLISH"
    await bus.close()


async def test_publish_rejects_on_closed_bus() -> None:
    bus = InMemoryMessageBus()
    await bus.close()
    agent = _StubAgent(bus=bus)
    with pytest.raises(RuntimeError, match="closed"):
        await agent.publish({"x": 1}, kind="technical_signal")


# --------------------------------------------------------------------------- #
# Redis fallback
# --------------------------------------------------------------------------- #


def test_redact_strips_credentials() -> None:
    """A password in the URL must never reach the log store."""
    from shared.messaging import _redact_redis_url

    assert (
        _redact_redis_url("redis://user:hunter2@cache.internal:6379/0")
        == "redis://<redacted>@cache.internal:6379/0"
    )


def test_redact_leaves_a_credential_free_url_untouched() -> None:
    from shared.messaging import _redact_redis_url

    assert _redact_redis_url("redis://redis:6379/0") == "redis://redis:6379/0"


def test_redact_handles_a_password_only_url() -> None:
    from shared.messaging import _redact_redis_url

    assert _redact_redis_url("redis://:pw@host:6379") == "redis://<redacted>@host:6379"


async def test_create_message_bus_falls_back_when_ping_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unreachable Redis must degrade, not raise."""
    from shared import messaging
    from shared.config import Settings

    class _DeadBus:
        def __init__(self, _url: str) -> None:
            pass

        async def ping(self) -> bool:
            raise ConnectionRefusedError(111, "Connection refused")

    monkeypatch.setattr(messaging, "RedisMessageBus", _DeadBus)
    settings = Settings(redis_url="redis://redis:6379/0", llm_provider="none")
    bus = await messaging.create_message_bus(settings)
    assert isinstance(bus, messaging.InMemoryMessageBus)


async def test_create_message_bus_logs_error_with_redacted_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The degradation must be loud and must name the unreachable target.

    A silent fallback is how a nine-day Redis outage went unnoticed, so the log
    is captured and asserted to carry the URL with credentials stripped.
    """
    from shared import messaging
    from shared.config import Settings

    class _DeadBus:
        def __init__(self, _url: str) -> None:
            pass

        async def ping(self) -> bool:
            raise ConnectionRefusedError(111, "Connection refused")

    events: list[tuple[str, dict[str, object]]] = []

    def _capture(event: str, *args: object, **kwargs: object) -> None:
        events.append((event, kwargs))

    monkeypatch.setattr(messaging, "RedisMessageBus", _DeadBus)
    monkeypatch.setattr(messaging._logger, "error", _capture)

    settings = Settings(redis_url="redis://user:hunter2@cache:6379/0", llm_provider="none")
    await messaging.create_message_bus(settings)

    assert len(events) == 1
    name, event = events[0]
    assert name == "bus.redis_degraded"
    assert event["url"] == "redis://<redacted>@cache:6379/0"
    assert "hunter2" not in str(event)
    assert "Connection refused" in str(event["error"])
