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


class KeyedFixedWindowLimiter:
    """Per-key fixed-window counter, for rejecting rather than queueing.

    :class:`AsyncRateLimiter` blocks a caller until the window allows another call,
    which is right for protecting an upstream API. Credential endpoints want the
    opposite: the request is *rejected* so a password guesser learns nothing and the
    caller sees a 429 rather than a hang.

    Keys are tracked with an idle TTL so a long-running process does not accumulate
    an entry for every address that ever connects. This is per-process state: behind
    more than one worker the effective ceiling is ``max_calls`` times the worker
    count. That is an accepted trade for a dependency-free limiter; put Redis in
    front of it if the ceiling ever needs to be exact.
    """

    def __init__(self, max_calls: int, period_seconds: float, *, idle_seconds: float | None = None):
        if max_calls <= 0:
            raise ValueError("max_calls must be positive")
        if period_seconds <= 0:
            raise ValueError("period_seconds must be positive")
        self._max_calls = max_calls
        self._period = period_seconds
        self._idle = idle_seconds if idle_seconds is not None else period_seconds * 2
        # key -> (window_start, count, last_seen)
        self._entries: dict[str, tuple[float, int, float]] = {}
        self._lock = asyncio.Lock()

    async def hit(self, key: str, *, now: float | None = None) -> tuple[bool, float]:
        """Record an attempt for ``key``.

        Returns ``(allowed, retry_after_seconds)``. ``retry_after_seconds`` is ``0``
        when the attempt was allowed, otherwise how long until the window rolls over.
        """
        moment = time.monotonic() if now is None else now
        async with self._lock:
            self._evict(moment)
            window_start, count, _ = self._entries.get(key, (moment, 0, moment))
            if moment - window_start >= self._period:
                window_start, count = moment, 0
            if count >= self._max_calls:
                self._entries[key] = (window_start, count, moment)
                return False, max(self._period - (moment - window_start), 0.0)
            self._entries[key] = (window_start, count + 1, moment)
            return True, 0.0

    def reset(self, key: str) -> None:
        """Forget ``key``, e.g. after a successful sign-in."""
        self._entries.pop(key, None)

    def _evict(self, moment: float) -> None:
        stale = [k for k, (_, _, seen) in self._entries.items() if moment - seen > self._idle]
        for key in stale:
            del self._entries[key]
