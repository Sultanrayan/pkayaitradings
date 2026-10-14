"""Tests for the anti-bot signals protecting login and registration.

The captcha itself is a network call and is mocked; what matters here is that every
check refuses the scripted case and passes the human one.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from orchestrator import antibot
from shared.config import Settings
from shared.utils.rate_limit import KeyedFixedWindowLimiter

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
)


def make_settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "recaptcha_min_form_seconds": 2.0,
        "recaptcha_max_form_seconds": 86_400.0,
        "auth_register_attempts_per_window": 3,
        "auth_rate_limit_window_seconds": 900,
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


NOW = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)


# ---------------------------------------------------------------- honeypot


@pytest.mark.parametrize("value", ["", "   ", None])
def test_honeypot_ignores_empty_values(value: str | None) -> None:
    assert antibot.honeypot_tripped(value) is False


@pytest.mark.parametrize("value", ["http://spam.example", "buy pills", "0"])
def test_honeypot_trips_on_any_content(value: str) -> None:
    assert antibot.honeypot_tripped(value) is True


# ------------------------------------------------------------------- timing


def test_timing_accepts_a_human_pace() -> None:
    settings = make_settings()
    started = (NOW - timedelta(seconds=9)).timestamp()
    ok, reason = antibot.timing_verdict(started, settings, now=NOW)
    assert ok is True
    assert reason is None


def test_timing_rejects_an_impossible_submit() -> None:
    settings = make_settings()
    started = (NOW - timedelta(milliseconds=200)).timestamp()
    ok, reason = antibot.timing_verdict(started, settings, now=NOW)
    assert ok is False
    assert reason == "Submitted too quickly"


def test_timing_rejects_a_replayed_timestamp() -> None:
    settings = make_settings()
    started = (NOW - timedelta(days=3)).timestamp()
    ok, reason = antibot.timing_verdict(started, settings, now=NOW)
    assert ok is False
    assert reason == "Stale form submission"


def test_timing_is_skipped_when_the_client_omits_it() -> None:
    """Absent is not a failure: refusing here would break non-browser clients."""
    settings = make_settings()
    for value in (0.0, -1.0):
        ok, reason = antibot.timing_verdict(value, settings, now=NOW)
        assert ok is True
        assert reason is None


# ------------------------------------------------------------ request shape


def test_shape_accepts_a_typical_browser() -> None:
    ok, reason = antibot.request_shape_verdict(
        user_agent=BROWSER_UA, accept_language="en-GB,en;q=0.9"
    )
    assert ok is True
    assert reason is None


def test_shape_rejects_a_missing_user_agent() -> None:
    ok, reason = antibot.request_shape_verdict(user_agent=None, accept_language="en-GB")
    assert ok is False
    assert reason == "Missing user agent"


def test_shape_rejects_a_blank_user_agent() -> None:
    ok, reason = antibot.request_shape_verdict(user_agent="   ", accept_language="en-GB")
    assert ok is False
    assert reason == "Missing user agent"


def test_shape_allows_a_missing_accept_language() -> None:
    """Omitting Accept-Language is normal and must not lock anyone out."""
    ok, reason = antibot.request_shape_verdict(user_agent=BROWSER_UA, accept_language=None)
    assert ok is True
    assert reason is None


@pytest.mark.parametrize(
    "agent",
    [
        "Scrapy/2.11",
        "Mozilla/5.0 (compatible; Googlebot/2.1)",
        "Mozilla/5.0 (compatible; bingbot/2.0)",
        "HeadlessChrome/140.0.0.0",
        "python-requests/2.32.0 | some-crawler",
    ],
)
def test_shape_rejects_automated_browsers(agent: str) -> None:
    ok, reason = antibot.request_shape_verdict(user_agent=agent, accept_language="en")
    assert ok is False
    assert reason == "Automated user agent"


@pytest.mark.parametrize(
    "agent",
    [
        # Legitimate developer clients. This product publishes an API and its docs
        # tell people to use curl, so these must NOT be blocked.
        "curl/8.5.0",
        "python-requests/2.32.0",
        "python-httpx/0.27.0",
        "Go-http-client/2.0",
        "okhttp/5.0",
        "Wget/1.21",
    ],
)
def test_shape_allows_http_clients(agent: str) -> None:
    ok, reason = antibot.request_shape_verdict(user_agent=agent, accept_language=None)
    assert ok is True
    assert reason is None


# --------------------------------------------------------------- rate limit


async def test_keyed_limiter_allows_up_to_the_ceiling() -> None:
    limiter = KeyedFixedWindowLimiter(3, 900.0)
    for _ in range(3):
        allowed, retry_after = await limiter.hit("1.2.3.4", now=0.0)
        assert allowed is True
        assert retry_after == 0.0

    allowed, retry_after = await limiter.hit("1.2.3.4", now=1.0)
    assert allowed is False
    assert retry_after == pytest.approx(899.0)


async def test_keyed_limiter_is_per_key() -> None:
    limiter = KeyedFixedWindowLimiter(1, 900.0)
    assert (await limiter.hit("a", now=0.0))[0] is True
    assert (await limiter.hit("a", now=0.0))[0] is False
    assert (await limiter.hit("b", now=0.0))[0] is True


async def test_keyed_limiter_window_rolls_over() -> None:
    limiter = KeyedFixedWindowLimiter(1, 60.0)
    assert (await limiter.hit("a", now=0.0))[0] is True
    assert (await limiter.hit("a", now=30.0))[0] is False
    assert (await limiter.hit("a", now=61.0))[0] is True


def test_keyed_limiter_rejects_nonsense_settings() -> None:
    with pytest.raises(ValueError, match="max_calls"):
        KeyedFixedWindowLimiter(0, 60.0)
    with pytest.raises(ValueError, match="period_seconds"):
        KeyedFixedWindowLimiter(1, 0.0)


async def test_keyed_limiter_evicts_idle_keys() -> None:
    limiter = KeyedFixedWindowLimiter(1, 60.0, idle_seconds=120.0)
    await limiter.hit("a", now=0.0)
    await limiter.hit("b", now=500.0)
    # "a" was idle long enough to be dropped, so the counter is gone entirely.
    assert len(limiter._entries) == 1
    assert "b" in limiter._entries


async def test_keyed_limiter_reset_forgets_a_key() -> None:
    limiter = KeyedFixedWindowLimiter(1, 60.0)
    await limiter.hit("a", now=0.0)
    assert (await limiter.hit("a", now=0.0))[0] is False
    limiter.reset("a")
    assert (await limiter.hit("a", now=0.0))[0] is True


async def test_register_rate_uses_the_configured_ceiling() -> None:
    settings = make_settings(auth_register_attempts_per_window=2)
    limiter = antibot.register_limiter(settings)
    assert (await limiter.hit("register:9.9.9.9", now=0.0))[0] is True
    assert (await limiter.hit("register:9.9.9.9", now=0.0))[0] is True
    assert (await limiter.hit("register:9.9.9.9", now=0.0))[0] is False


# --------------------------------------------------------------- defaults


def test_antibot_defaults_are_off_unless_configured() -> None:
    """An unconfigured deployment must not start rejecting traffic."""
    settings = Settings()
    assert settings.recaptcha_secret_key == ""
    assert settings.recaptcha_min_form_seconds == 2.0
    assert settings.auth_register_attempts_per_window == 10
    assert settings.auth_login_attempts_per_window == 10
    assert settings.auth_rate_limit_window_seconds == 900


def test_secret_is_never_exposed_by_the_api() -> None:
    """The secret must not be reachable from any response model."""
    from orchestrator.main import AuthConfigResponse, PlanInfoResponse

    for model in (AuthConfigResponse, PlanInfoResponse):
        assert "recaptcha_secret_key" not in model.model_fields
