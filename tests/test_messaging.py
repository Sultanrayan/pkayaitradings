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
