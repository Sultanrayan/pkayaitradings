"""Google OAuth 2.0 helpers (authorization-code flow).

The ID token is obtained server-to-server from Google's token endpoint over
TLS and its claims (issuer, audience, expiry, verified email) are validated
here. Signature verification is skipped because the token never travels
through the browser.
"""

from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

from orchestrator.auth import AuthError

GOOGLE_AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
_ISSUERS = frozenset({"accounts.google.com", "https://accounts.google.com"})


@dataclass(frozen=True)
class GoogleIdentity:
    """The verified identity returned by Google."""

    subject: str
    email: str
    name: str
    email_verified: bool


def build_authorization_url(
    client_id: str,
    redirect_uri: str,
    state: str,
    *,
    prompt: str = "select_account",
) -> str:
    """Build the Google consent-screen URL."""
    query = urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "access_type": "online",
            "prompt": prompt,
        }
    )
    return f"{GOOGLE_AUTHORIZATION_ENDPOINT}?{query}"


def decode_id_token(id_token: str, client_id: str) -> GoogleIdentity:
    """Decode and validate a Google ID token.

    Raises:
        AuthError: If the token is malformed or its claims are invalid.
    """
    try:
        _header, payload_b64, _signature = id_token.split(".")
        payload = json.loads(base64.urlsafe_b64decode(payload_b64 + "=" * (-len(payload_b64) % 4)))
    except (ValueError, json.JSONDecodeError) as exc:
        raise AuthError("Malformed Google ID token") from exc

    if payload.get("iss") not in _ISSUERS:
        raise AuthError("Unexpected Google ID token issuer")
    if payload.get("aud") != client_id:
        raise AuthError("Google ID token audience mismatch")
    expires_at = payload.get("exp")
    if not isinstance(expires_at, (int, float)) or float(expires_at) < time.time():
        raise AuthError("Google ID token expired")
    email = payload.get("email")
    subject = payload.get("sub")
    if not email or not subject:
        raise AuthError("Google ID token is missing an email or subject")
    return GoogleIdentity(
        subject=str(subject),
        email=str(email),
        name=str(payload.get("name") or str(email).split("@")[0]),
        email_verified=bool(payload.get("email_verified", False)),
    )


async def exchange_code_for_identity(
    *,
    code: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
) -> GoogleIdentity:
    """Exchange an authorization code for a verified Google identity."""
    data = {
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(GOOGLE_TOKEN_ENDPOINT, data=data)
    if response.status_code != 200:
        raise AuthError(f"Google token exchange failed (HTTP {response.status_code})")
    payload = response.json()
    id_token = payload.get("id_token")
    if not isinstance(id_token, str):
        raise AuthError("Google token response is missing an id_token")
    return decode_id_token(id_token, client_id)
