"""IP-based rate limiting for login attempts.

Tracks failed login attempts by IP address. After 3 failed attempts, the IP
is blocked from further login attempts for 1 hour.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class LoginAttempt:
    """Record of login attempts from an IP address."""

    failed_count: int
    last_failed_at: float
    blocked_until: float | None = None


class LoginRateLimiter:
    """Track and enforce login attempt limits by IP address.

    After MAX_ATTEMPTS failed logins, the IP is blocked for BLOCK_DURATION_SECONDS.
    The counter resets after RESET_WINDOW_SECONDS of no failed attempts.

    Args:
        now: Clock returning the current time as a Unix timestamp. Injectable so
            the reset and expiry windows can be tested by advancing time rather
            than by sleeping, which was the suite's only wall-clock dependency.
    """

    MAX_ATTEMPTS = 3
    BLOCK_DURATION_SECONDS = 3600  # 1 hour
    RESET_WINDOW_SECONDS = 300  # 5 minutes

    def __init__(self, *, now: Callable[[], float] | None = None) -> None:
        self._attempts: dict[str, LoginAttempt] = {}
        self._now: Callable[[], float] = now or time.time

    def is_blocked(self, ip: str) -> bool:
        """Check if an IP address is currently blocked."""
        if not ip:
            return False

        attempt = self._attempts.get(ip)
        if not attempt:
            return False

        # Check if blocked and block period hasn't expired
        if attempt.blocked_until:
            if self._now() < attempt.blocked_until:
                return True
            # Block period expired, reset
            del self._attempts[ip]
            return False

        return False

    def record_failed_attempt(self, ip: str) -> None:
        """Record a failed login attempt for an IP address."""
        if not ip:
            return

        now = self._now()
        attempt = self._attempts.get(ip)

        if not attempt:
            # First failed attempt
            self._attempts[ip] = LoginAttempt(
                failed_count=1,
                last_failed_at=now
            )
            return

        # Check if we should reset the counter (no failures in RESET_WINDOW)
        if now - attempt.last_failed_at > self.RESET_WINDOW_SECONDS:
            self._attempts[ip] = LoginAttempt(
                failed_count=1,
                last_failed_at=now
            )
            return

        # Increment failed count
        attempt.failed_count += 1
        attempt.last_failed_at = now

        # Block if threshold reached
        if attempt.failed_count >= self.MAX_ATTEMPTS:
            attempt.blocked_until = now + self.BLOCK_DURATION_SECONDS

    def record_successful_login(self, ip: str) -> None:
        """Clear failed attempts after a successful login."""
        if ip and ip in self._attempts:
            del self._attempts[ip]

    def get_remaining_attempts(self, ip: str) -> int:
        """Get the number of remaining login attempts for an IP."""
        if not ip:
            return self.MAX_ATTEMPTS

        attempt = self._attempts.get(ip)
        if not attempt:
            return self.MAX_ATTEMPTS

        now = self._now()

        # If blocked, no attempts remaining
        if attempt.blocked_until and now < attempt.blocked_until:
            return 0

        # If reset window passed, full attempts available
        if now - attempt.last_failed_at > self.RESET_WINDOW_SECONDS:
            return self.MAX_ATTEMPTS

        return max(0, self.MAX_ATTEMPTS - attempt.failed_count)

    def get_block_time_remaining(self, ip: str) -> int:
        """Get seconds remaining in block period, or 0 if not blocked."""
        if not ip:
            return 0

        attempt = self._attempts.get(ip)
        if not attempt or not attempt.blocked_until:
            return 0

        remaining = int(attempt.blocked_until - self._now())
        return max(0, remaining)
