"""Tests for the Technical Analyst agent."""

from __future__ import annotations

import asyncio
from typing import Any

from agents.technical_analyst.agent import TechnicalAnalystAgent
from shared.messaging import InMemoryMessageBus
from shared.schemas.enums import Direction, Timeframe
from shared.schemas.market import OhlcSeries
from shared.schemas.messages import AgentMessage
from tests.test_strategy import make_series


class _StubClient:
    def __init__(self, series: OhlcSeries) -> None:
        self._series = series
        self.calls: list[dict[str, Any]] = []

    async def get_ohlc(self, symbol: str, *, interval: Timeframe, limit: int) -> OhlcSeries:
        self.calls.append({"symbol": symbol, "interval": interval, "limit": limit})
        return self._series

    async def close(self) -> None:
        return None


async def _first_message(bus: InMemoryMessageBus, pattern: str) -> AgentMessage:
    async for message in bus.subscribe(pattern):
        return message
    raise AssertionError("no message received")  # pragma: no cover


async def test_analyze_returns_bullish_signal_for_uptrend() -> None:
    client = _StubClient(make_series(300, drift=0.6))
    agent = TechnicalAnalystAgent(client=client)

    signal = await agent.analyze("XAUUSD", Timeframe.H1)

    assert signal.symbol == "XAUUSD"
    assert signal.signal is Direction.BULLISH
    assert 0.0 <= signal.confidence <= 1.0
    assert client.calls[0]["symbol"] == "XAUUSD"
    assert client.calls[0]["interval"] is Timeframe.H1


async def test_run_publishes_signal() -> None:
    bus = InMemoryMessageBus()
    client = _StubClient(make_series(300, drift=-0.6))
    agent = TechnicalAnalystAgent(client=client, bus=bus)

    task = asyncio.create_task(_first_message(bus, "signals.technical_analyst"))
    await asyncio.sleep(0)
    signal = await agent.run("BTCUSD", Timeframe.H4)
    message = await asyncio.wait_for(task, timeout=2.0)

    assert signal.signal is Direction.BEARISH
    assert message.kind == "technical_signal"
    assert message.payload["symbol"] == "BTCUSD"


async def test_stop_does_not_close_injected_client() -> None:
    client = _StubClient(make_series(100))
    agent = TechnicalAnalystAgent(client=client)
    await agent.stop()
    assert client.calls == []
