"""Tests for login rate limiting functionality.

The limiter takes an injectable clock, so the reset and block-expiry windows are
exercised by advancing time rather than by sleeping. This removes the suite's
only wall-clock dependency, which previously made these two tests the only
places where timing affected the result.
"""

from orchestrator.login_rate_limiter import LoginRateLimiter


class _FakeClock:
    """Manually advanced clock."""

    def __init__(self, start: float = 1_000_000.0) -> None:
        self.value = start

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def test_first_attempt_not_blocked():
    """First login attempt should not be blocked."""
    limiter = LoginRateLimiter()
    assert not limiter.is_blocked("192.168.1.1")
    assert limiter.get_remaining_attempts("192.168.1.1") == 3


def test_failed_attempts_tracked():
    """Failed login attempts should be tracked."""
    limiter = LoginRateLimiter()
    ip = "192.168.1.1"

    limiter.record_failed_attempt(ip)
    assert limiter.get_remaining_attempts(ip) == 2
    assert not limiter.is_blocked(ip)

    limiter.record_failed_attempt(ip)
    assert limiter.get_remaining_attempts(ip) == 1
    assert not limiter.is_blocked(ip)


def test_blocked_after_max_attempts():
    """IP should be blocked after 3 failed attempts."""
    limiter = LoginRateLimiter()
    ip = "192.168.1.1"

    # Record 3 failed attempts
    limiter.record_failed_attempt(ip)
    limiter.record_failed_attempt(ip)
    limiter.record_failed_attempt(ip)

    # Should now be blocked
    assert limiter.is_blocked(ip)
    assert limiter.get_remaining_attempts(ip) == 0


def test_block_duration():
    """Block should last for the configured duration."""
    limiter = LoginRateLimiter()
    ip = "192.168.1.1"

    # Record 3 failed attempts to trigger block
    limiter.record_failed_attempt(ip)
    limiter.record_failed_attempt(ip)
    limiter.record_failed_attempt(ip)

    # Check block time remaining
    block_time = limiter.get_block_time_remaining(ip)
    assert block_time > 3590  # Should be close to 1 hour (3600 seconds)
    assert block_time <= 3600


def test_successful_login_clears_attempts():
    """Successful login should clear failed attempts."""
    limiter = LoginRateLimiter()
    ip = "192.168.1.1"

    # Record failed attempts
    limiter.record_failed_attempt(ip)
    limiter.record_failed_attempt(ip)
    assert limiter.get_remaining_attempts(ip) == 1

    # Successful login clears
    limiter.record_successful_login(ip)
    assert limiter.get_remaining_attempts(ip) == 3
    assert not limiter.is_blocked(ip)


def test_reset_window():
    """Failed attempts should reset after the reset window."""
    clock = _FakeClock()
    limiter = LoginRateLimiter(now=clock)
    limiter.RESET_WINDOW_SECONDS = 1  # Short window, advanced by the fake clock
    ip = "192.168.1.1"

    # Record failed attempts
    limiter.record_failed_attempt(ip)
    limiter.record_failed_attempt(ip)
    assert limiter.get_remaining_attempts(ip) == 1

    # Advance past the reset window instead of sleeping.
    clock.advance(1.1)

    # Next attempt should reset the counter
    limiter.record_failed_attempt(ip)
    assert limiter.get_remaining_attempts(ip) == 2


def test_different_ips_tracked_separately():
    """Different IPs should have separate attempt counters."""
    limiter = LoginRateLimiter()
    ip1 = "192.168.1.1"
    ip2 = "192.168.1.2"

    limiter.record_failed_attempt(ip1)
    limiter.record_failed_attempt(ip1)

    limiter.record_failed_attempt(ip2)

    assert limiter.get_remaining_attempts(ip1) == 1
    assert limiter.get_remaining_attempts(ip2) == 2


def test_none_ip_handling():
    """None or empty IP should be handled gracefully."""
    limiter = LoginRateLimiter()

    assert not limiter.is_blocked(None)
    assert not limiter.is_blocked("")

    limiter.record_failed_attempt(None)
    limiter.record_failed_attempt("")

    # Should not affect anything
    assert limiter.get_remaining_attempts(None) == 3
    assert limiter.get_remaining_attempts("") == 3


def test_block_expires():
    """Block should expire after the block duration."""
    clock = _FakeClock()
    limiter = LoginRateLimiter(now=clock)
    limiter.BLOCK_DURATION_SECONDS = 1  # Short block, advanced by the fake clock
    ip = "192.168.1.1"

    # Trigger block
    limiter.record_failed_attempt(ip)
    limiter.record_failed_attempt(ip)
    limiter.record_failed_attempt(ip)

    assert limiter.is_blocked(ip)

    # Advance past the block instead of sleeping.
    clock.advance(1.1)

    # Should no longer be blocked
    assert not limiter.is_blocked(ip)
    assert limiter.get_remaining_attempts(ip) == 3


def test_block_time_remaining_uses_the_injected_clock():
    """The remaining-time report must come from the same clock, not wall time."""
    clock = _FakeClock()
    limiter = LoginRateLimiter(now=clock)
    limiter.BLOCK_DURATION_SECONDS = 60
    ip = "192.168.1.1"

    for _ in range(3):
        limiter.record_failed_attempt(ip)
    assert limiter.get_block_time_remaining(ip) == 60

    clock.advance(25)
    assert limiter.get_block_time_remaining(ip) == 35
