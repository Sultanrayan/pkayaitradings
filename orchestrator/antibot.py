"""Anti-bot signals for the credential endpoints.

Four independent checks, none of which is a substitute for reCAPTCHA:

* **Honeypot** — a field that is hidden from people and visible to form-filling
  bots. Anything in it is a script.
* **Form timing** — the client reports when the form was first rendered; a
  submission faster than a human could plausibly type is scripted.
* **Request shape** — a real browser sends a user-agent and an ``Accept-Language``.
  Missing or obviously automated ones are refused.
* **Rate limit** — per-IP ceilings on attempts, see
  :class:`shared.utils.rate_limit.KeyedFixedWindowLimiter`.

These are cheap and they remove the trivially scripted traffic that never bothers to
pretend. They are deliberately implemented and enforced **server-side**: anything
checked only in the browser is controlled by whoever is attacking it. The JavaScript
in the forms exists to collect these signals and render the widget, not to enforce
anything.

All checks return a neutral ``(True, None)`` when unconfigured, so development and
the test suite are unaffected.
"""

from __future__ import annotations

from datetime import UTC, datetime

from shared.config import Settings
from shared.utils.rate_limit import KeyedFixedWindowLimiter

#: Substrings that mark a user-agent as an automated *browser*, as opposed to an
#: HTTP client.
#:
#: Deliberately excludes ``curl``, ``python-requests``, ``httpx``, ``wget``,
#: ``okhttp``, ``go-http-client`` and friends. This product publishes an API, and a
#: developer registering an account from a script is a legitimate user — the docs
#: page for this very product tells people to use curl. Blocking those would reject
#: real sign-ups to no security benefit: anything scripted that gets that far still
#: has to clear reCAPTCHA, the honeypot and the timing check. A false positive here
#: locks out a real person, which is the worse failure.
BOT_MARKERS = (
    "bot",
    "crawler",
    "spider",
    "scrapy",
    "headlesschrome",
    "phantomjs",
    "puppeteer",
    "playwright",
)

#: A browser always sends a user-agent. Nothing else does.
_MISSING = ""


def honeypot_tripped(value: str | None) -> bool:
    """True when the hidden field carries anything at all."""
    return bool(value and value.strip())


def timing_verdict(
    form_started_at: float,
    settings: Settings,
    *,
    now: datetime | None = None,
) -> tuple[bool, str | None]:
    """Reject submissions that were too fast, or whose timestamp is implausible.

    ``form_started_at`` is epoch seconds from the browser. A missing or non-positive
    value disables the check rather than failing closed, because the field is only
    additive signal and refusing every request without it would break API clients.
    """
    if form_started_at <= 0:
        return True, None

    moment = now or datetime.now(UTC)
    elapsed = moment.timestamp() - form_started_at

    if elapsed < settings.recaptcha_min_form_seconds:
        return False, "Submitted too quickly"
    if elapsed > settings.recaptcha_max_form_seconds:
        return False, "Stale form submission"
    return True, None


def request_shape_verdict(
    *,
    user_agent: str | None,
    accept_language: str | None = None,
) -> tuple[bool, str | None]:
    """Reject requests that do not look like they came from a browser.

    ``accept_language`` is accepted for call-site symmetry but is deliberately not a
    rejection criterion: browsers can be configured to omit it, privacy extensions
    strip it, and plenty of legitimate clients never send it. Treating its absence
    as suspicious rejects real users for nothing.
    """
    del accept_language  # Recorded for future use; not a rejection signal.

    agent = (user_agent or "").strip()
    if agent == _MISSING:
        return False, "Missing user agent"

    lowered = agent.lower()
    if any(marker in lowered for marker in BOT_MARKERS):
        return False, "Automated user agent"

    return True, None


def register_limiter(settings: Settings) -> KeyedFixedWindowLimiter:
    """Per-IP limiter for account creation.

    Sign-in deliberately does **not** use this. It already has
    :class:`orchestrator.login_rate_limiter.LoginRateLimiter`, which blocks an IP
    for an hour after three *failed* attempts — a stricter rule than a flat attempt
    ceiling, and one that a caller cannot reset by simply succeeding. Adding a second
    login limiter on top would only create a way to lock out a shared address without
    stopping anything the existing one misses. Registration had no limiter at all,
    which is the gap this fills.
    """
    return KeyedFixedWindowLimiter(
        settings.auth_register_attempts_per_window,
        float(settings.auth_rate_limit_window_seconds),
    )


# Process-wide, created on first use so it picks up test settings.
_REGISTER_LIMITER: KeyedFixedWindowLimiter | None = None


async def check_register_rate(client_ip: str) -> tuple[bool, float]:
    """Record a registration attempt. Returns ``(allowed, retry_after)``."""
    global _REGISTER_LIMITER
    from shared.config import get_settings

    if _REGISTER_LIMITER is None:
        _REGISTER_LIMITER = register_limiter(get_settings())
    return await _REGISTER_LIMITER.hit(f"register:{client_ip}")


def reset_register_rate(client_ip: str) -> None:
    """Forget a client's registration counter."""
    if _REGISTER_LIMITER is not None:
        _REGISTER_LIMITER.reset(f"register:{client_ip}")
