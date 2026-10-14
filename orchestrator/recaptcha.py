"""Google reCAPTCHA v2 verification for the credential endpoints.

When ``RECAPTCHA_SECRET_KEY`` is not configured the check is skipped so local
development and the test suite keep working, matching how
:mod:`orchestrator.turnstile` behaves for the access-request form.

The secret is used here and nowhere else. It is never returned to a client, never
placed in a URL, and never logged.
"""

from __future__ import annotations

import httpx

from shared.config import get_settings


async def verify_recaptcha(token: str, *, remote_ip: str | None = None) -> bool:
    """Return True when the reCAPTCHA response token passes verification.

    A missing secret key disables the check (dev/test). A missing token is rejected
    whenever verification is enabled, and a transport failure is treated as a
    failure rather than being waved through.
    """
    settings = get_settings()
    if not settings.recaptcha_secret_key:
        return True
    if not token:
        return False

    payload = {
        "secret": settings.recaptcha_secret_key,
        "response": token,
    }
    if remote_ip:
        payload["remoteip"] = remote_ip

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(settings.recaptcha_verify_url, data=payload)
            response.raise_for_status()
            body = response.json()
    except (httpx.HTTPError, ValueError):
        return False

    return bool(body.get("success"))
