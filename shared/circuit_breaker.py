"""Circuit breaker that protects agents from repeated failures.

Implements the ``CLOSED / OPEN / HALF_OPEN`` state machine from the backend-v2
roadmap (Problem 2):

* ``CLOSED`` — calls flow normally. After ``failure_threshold`` consecutive
  failures the circuit trips to ``OPEN``.
* ``OPEN`` — calls are rejected immediately with :class:`CircuitOpenError` so a
  failing agent stops consuming resources. After ``recovery_timeout_seconds``
  the circuit transitions to ``HALF_OPEN`` on the next check.
* ``HALF_OPEN`` — a probe call is allowed through; a success closes the circuit,
  a failure trips it back to ``OPEN``.

The breaker is thread-safe (guarded by a lock) so it can be shared across async
tasks safely.
"""

from __future__ import annotations

import threading
import time
from enum import StrEnum


class CircuitState(StrEnum):
    """Lifecycle state of a :class:`CircuitBreaker`."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(RuntimeError):
    """Raised when a call is attempted while the circuit is open."""


class CircuitBreaker:
    """Failure counter and state machine guarding a single agent."""

    def __init__(
        self,
        *,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout_seconds: float = 300.0,
    ) -> None:
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be >= 1")
        if recovery_timeout_seconds <= 0:
            raise ValueError("recovery_timeout_seconds must be > 0")
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout_seconds = recovery_timeout_seconds
        self._failures = 0
        self._state = CircuitState.CLOSED
        self._opened_at: float | None = None
        self._lock = threading.Lock()

    @property
    def state(self) -> CircuitState:
        """Current state, promoting ``OPEN`` to ``HALF_OPEN`` after the timeout."""
        with self._lock:
            if (
                self._state is CircuitState.OPEN
                and self._opened_at is not None
                and time.monotonic() - self._opened_at >= self.recovery_timeout_seconds
            ):
                self._state = CircuitState.HALF_OPEN
            return self._state

    @property
    def failures(self) -> int:
        """Number of consecutive recorded failures."""
        with self._lock:
            return self._failures

    @property
    def is_open(self) -> bool:
        """Whether calls should be rejected right now."""
        return self.state is CircuitState.OPEN

    def record_success(self) -> None:
        """Reset the failure counter and close a half-open circuit."""
        with self._lock:
            self._failures = 0
            if self._state is not CircuitState.CLOSED:
                self._state = CircuitState.CLOSED
            self._opened_at = None

    def record_failure(self) -> None:
        """Count a failure, tripping the circuit once the threshold is reached."""
        with self._lock:
            self._failures += 1
            if self._failures >= self.failure_threshold:
                self._state = CircuitState.OPEN
                self._opened_at = time.monotonic()

    def __repr__(self) -> str:
        return (
            f"CircuitBreaker(name={self.name!r}, state={self.state.value}, "
            f"failures={self._failures})"
        )
