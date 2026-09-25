"""Tests for the BaseAgent circuit-breaker guard and output validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agents.base_agent import BaseAgent
from shared.circuit_breaker import CircuitOpenError
from shared.config import Settings
from shared.schemas.enums import AgentName, Direction, Timeframe
from shared.schemas.signals import TechnicalSignal


class _MinimalAgent(BaseAgent):
    """Concrete agent used to exercise the guarded execution path."""

    name = AgentName.TECHNICAL_ANALYST

    async def run(self) -> TechnicalSignal:  # type: ignore[override]
        raise NotImplementedError


def _signal() -> TechnicalSignal:
    return TechnicalSignal(
        symbol="XAUUSD", timeframe=Timeframe.H1, signal=Direction.BULLISH, confidence=0.8
    )


async def test_guarded_passes_valid_output() -> None:
    agent = _MinimalAgent(settings=Settings(circuit_breaker_failure_threshold=3))
    expected = _signal()

    async def operation() -> TechnicalSignal:
        return expected

    result = await agent._guarded(TechnicalSignal, operation)
    assert result is expected
    assert agent.breaker.failures == 0
    assert agent.breaker.is_open is False


async def test_guarded_rejects_malformed_output() -> None:
    agent = _MinimalAgent(settings=Settings(circuit_breaker_failure_threshold=3))

    async def operation() -> dict[str, object]:
        return {"symbol": "XAUUSD"}  # missing required fields

    with pytest.raises(ValidationError):
        await agent._guarded(TechnicalSignal, operation)
    assert agent.breaker.failures == 1


async def test_guarded_trips_breaker_on_repeated_failures() -> None:
    agent = _MinimalAgent(settings=Settings(circuit_breaker_failure_threshold=2))

    async def failing() -> TechnicalSignal:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        await agent._guarded(TechnicalSignal, failing)
    assert agent.breaker.is_open is False

    with pytest.raises(RuntimeError):
        await agent._guarded(TechnicalSignal, failing)
    assert agent.breaker.is_open is True

    with pytest.raises(CircuitOpenError):
        await agent._guarded(TechnicalSignal, failing)


async def test_guarded_recovers_after_half_open_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeClock:
        def __init__(self) -> None:
            self.now = 1_000.0

        def __call__(self) -> float:
            return self.now

    clock = _FakeClock()
    monkeypatch.setattr("shared.circuit_breaker.time.monotonic", clock)
    agent = _MinimalAgent(
        settings=Settings(circuit_breaker_failure_threshold=1, circuit_breaker_recovery_timeout_seconds=60.0)
    )

    async def failing() -> TechnicalSignal:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        await agent._guarded(TechnicalSignal, failing)
    assert agent.breaker.is_open is True

    clock.now += 61.0  # recovery timeout elapses -> HALF_OPEN probe allowed

    async def working() -> TechnicalSignal:
        return _signal()

    result = await agent._guarded(TechnicalSignal, working)
    assert result is not None
    assert agent.breaker.state.value == "closed"
    assert agent.breaker.is_open is False
