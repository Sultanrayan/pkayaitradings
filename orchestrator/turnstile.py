"""Cloudflare Turnstile verification for registration endpoints.

When ``TURNSTILE_SECRET_KEY`` is not configured the check is skipped so local
development and the test suite keep working.
"""

from __future__ import annotations

import httpx

from shared.config import get_settings

_TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


async def verify_turnstile(token: str, *, remote_ip: str | None = None) -> bool:
    """Return True when the Turnstile response token passes verification.

    A missing secret key disables the check (dev/test). A missing or invalid
    token is rejected when verification is enabled.
    """
    settings = get_settings()
    if not settings.turnstile_secret_key:
        return True
    if not token:
        return False
    payload = {
        "secret": settings.turnstile_secret_key,
        "response": token,
    }
    if remote_ip:
        payload["remoteip"] = remote_ip
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(settings.turnstile_verify_url, data=payload)
            response.raise_for_status()
            return bool(response.json().get("success"))
    except httpx.HTTPError:
        return False
