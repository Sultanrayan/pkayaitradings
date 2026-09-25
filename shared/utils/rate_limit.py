"""A minimal, dependency-free asynchronous rate limiter.

Implements a fixed-window counter, matching biquote's documented per-minute
quota semantics. The limiter is safe for concurrent use within a single event
loop.
"""

from __future__ import annotations

import asyncio
import time


class AsyncRateLimiter:
    """Limit work to ``max_calls`` per ``period_seconds`` window.

    Example:
        >>> limiter = AsyncRateLimiter(max_calls=100, period_seconds=60)
        >>> await limiter.acquire()
    """

    def __init__(self, max_calls: int, period_seconds: float) -> None:
        if max_calls <= 0:
            raise ValueError("max_calls must be positive")
        if period_seconds <= 0:
            raise ValueError("period_seconds must be positive")
        self._max_calls = max_calls
        self._period = period_seconds
        self._window_start = 0.0
        self._count = 0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Block until a call is permitted in the current window."""
        while True:
            async with self._lock:
                now = time.monotonic()
                if now - self._window_start >= self._period:
                    self._window_start = now
                    self._count = 0
                if self._count < self._max_calls:
                    self._count += 1
                    return
                wait_for = self._period - (now - self._window_start)
            await asyncio.sleep(max(wait_for, 0.001))

    @property
    def remaining(self) -> int:
        """Calls remaining in the current window (best-effort)."""
        if time.monotonic() - self._window_start >= self._period:
            return self._max_calls
        return max(self._max_calls - self._count, 0)
