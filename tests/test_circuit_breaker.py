"""Tests for the shared circuit breaker."""

from __future__ import annotations

import pytest

from shared.circuit_breaker import CircuitBreaker, CircuitOpenError, CircuitState


def test_closed_initial_state() -> None:
    breaker = CircuitBreaker(name="technical")
    assert breaker.state is CircuitState.CLOSED
    assert breaker.failures == 0
    assert breaker.is_open is False


def test_opens_after_failure_threshold() -> None:
    breaker = CircuitBreaker(name="news", failure_threshold=3)
    breaker.record_failure()
    breaker.record_failure()
    assert breaker.state is CircuitState.CLOSED
    breaker.record_failure()
    assert breaker.state is CircuitState.OPEN
    assert breaker.is_open is True


def test_success_resets_failure_count() -> None:
    breaker = CircuitBreaker(name="risk", failure_threshold=3)
    breaker.record_failure()
    breaker.record_failure()
    breaker.record_success()
    assert breaker.failures == 0
    assert breaker.state is CircuitState.CLOSED


class _FakeClock:
    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now


def test_half_open_allows_probe_after_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = _FakeClock()
    monkeypatch.setattr("shared.circuit_breaker.time.monotonic", clock)
    breaker = CircuitBreaker(name="decision", failure_threshold=2, recovery_timeout_seconds=60.0)
    breaker.record_failure()
    breaker.record_failure()
    assert breaker.state is CircuitState.OPEN

    clock.now += 61.0
    assert breaker.state is CircuitState.HALF_OPEN
    assert breaker.is_open is False


def test_half_open_success_closes(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = _FakeClock()
    monkeypatch.setattr("shared.circuit_breaker.time.monotonic", clock)
    breaker = CircuitBreaker(name="decision", failure_threshold=2, recovery_timeout_seconds=60.0)
    breaker.record_failure()
    breaker.record_failure()
    clock.now += 61.0
    assert breaker.state is CircuitState.HALF_OPEN

    breaker.record_success()
    assert breaker.state is CircuitState.CLOSED
    assert breaker.failures == 0


def test_half_open_failure_reopens(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = _FakeClock()
    monkeypatch.setattr("shared.circuit_breaker.time.monotonic", clock)
    breaker = CircuitBreaker(name="decision", failure_threshold=2, recovery_timeout_seconds=60.0)
    breaker.record_failure()
    breaker.record_failure()
    clock.now += 61.0
    assert breaker.state is CircuitState.HALF_OPEN

    breaker.record_failure()
    assert breaker.state is CircuitState.OPEN


def test_rejects_invalid_parameters() -> None:
    with pytest.raises(ValueError, match="failure_threshold"):
        CircuitBreaker(name="x", failure_threshold=0)
    with pytest.raises(ValueError, match="recovery_timeout"):
        CircuitBreaker(name="x", recovery_timeout_seconds=0.0)


def test_circuit_open_error_is_runtime_error() -> None:
    assert issubclass(CircuitOpenError, RuntimeError)
