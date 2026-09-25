"""Tests for Google OAuth: helpers and the auth endpoints."""

from __future__ import annotations

import base64
import json
import time
from unittest.mock import AsyncMock

import httpx
import pytest

from orchestrator import main as orchestrator_main
from orchestrator.auth import AuthError, sign_payload
from orchestrator.oauth import (
    GoogleIdentity,
    build_authorization_url,
    decode_id_token,
)
from shared.config import Settings

SECRET = "test-secret"
CLIENT_ID = "client-id.apps.googleusercontent.com"


def _b64(payload: dict[str, object]) -> str:
    raw = json.dumps(payload, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def make_id_token(**overrides: object) -> str:
    payload: dict[str, object] = {
        "iss": "https://accounts.google.com",
        "aud": CLIENT_ID,
        "exp": int(time.time()) + 3600,
        "email": "user@example.com",
        "email_verified": True,
        "sub": "google-subject-1",
        "name": "Google User",
    }
    payload.update(overrides)
    return f"{_b64({'alg': 'none', 'typ': 'JWT'})}.{_b64(payload)}.signature"


def google_settings() -> Settings:
    return Settings(
        google_client_id=CLIENT_ID,
        google_client_secret="client-secret",
        google_redirect_uri="http://test/api/v1/auth/google/callback",
        frontend_url="http://frontend.test",
        auth_secret=SECRET,
    )


def test_build_authorization_url() -> None:
    url = build_authorization_url(CLIENT_ID, "http://cb", "state-123")
    assert url.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    assert "client_id=client-id" in url
    assert "state=state-123" in url
    assert "scope=openid" in url


def test_decode_id_token_valid() -> None:
    identity = decode_id_token(make_id_token(), CLIENT_ID)
    assert identity.email == "user@example.com"
    assert identity.subject == "google-subject-1"
    assert identity.email_verified is True


@pytest.mark.parametrize(
    "overrides",
    [
        {"iss": "https://evil.example"},
        {"aud": "someone-else"},
        {"exp": int(time.time()) - 10},
        {"email": ""},
        {"sub": ""},
    ],
)
def test_decode_id_token_rejects_bad_claims(overrides: dict[str, object]) -> None:
    with pytest.raises(AuthError):
        decode_id_token(make_id_token(**overrides), CLIENT_ID)


def test_decode_id_token_malformed() -> None:
    with pytest.raises(AuthError):
        decode_id_token("not-a-jwt", CLIENT_ID)


@pytest.fixture
async def client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=orchestrator_main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client


async def test_auth_config_reports_google_disabled(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(orchestrator_main, "get_settings", lambda: Settings())
    response = await client.get("/api/v1/auth/config")
    assert response.status_code == 200
    assert response.json() == {"google": False}


async def test_google_login_redirects_when_configured(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(orchestrator_main, "get_settings", google_settings)
    response = await client.get("/api/v1/auth/google/login", follow_redirects=False)
    assert response.status_code == 307
    location = response.headers["location"]
    assert location.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    assert "state=" in location


async def test_google_login_unconfigured(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(orchestrator_main, "get_settings", lambda: Settings())
    response = await client.get("/api/v1/auth/google/login", follow_redirects=False)
    assert response.status_code == 503


async def test_google_callback_issues_token(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = google_settings()
    monkeypatch.setattr(orchestrator_main, "get_settings", lambda: settings)
    identity = GoogleIdentity(
        subject="google-subject-2",
        email=f"callback-{time.time_ns()}@example.com",
        name="Callback User",
        email_verified=True,
    )
    monkeypatch.setattr(
        orchestrator_main, "exchange_code_for_identity", AsyncMock(return_value=identity)
    )
    state = sign_payload({"nonce": "n", "exp": int(time.time()) + 60}, SECRET)

    response = await client.get(
        "/api/v1/auth/google/callback",
        params={"code": "auth-code", "state": state},
        follow_redirects=False,
    )
    assert response.status_code == 307
    location = response.headers["location"]
    assert location == "http://frontend.test/dashboard"
    token_cookie = response.cookies.get("pkay_token")
    assert token_cookie
    assert token_cookie != ""


async def test_google_callback_honors_next_in_state(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = google_settings()
    monkeypatch.setattr(orchestrator_main, "get_settings", lambda: settings)
    identity = GoogleIdentity(
        subject="google-subject-next",
        email=f"next-{time.time_ns()}@example.com",
        name="Next User",
        email_verified=True,
    )
    monkeypatch.setattr(
        orchestrator_main, "exchange_code_for_identity", AsyncMock(return_value=identity)
    )
    state = sign_payload(
        {"nonce": "n", "exp": int(time.time()) + 60, "next": "/pkay-control-x7q9"}, SECRET
    )

    response = await client.get(
        "/api/v1/auth/google/callback",
        params={"code": "auth-code", "state": state},
        follow_redirects=False,
    )
    assert response.status_code == 307
    assert response.headers["location"] == "http://frontend.test/pkay-control-x7q9"
    assert response.cookies.get("pkay_token")


async def test_google_callback_rejects_external_next(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = google_settings()
    monkeypatch.setattr(orchestrator_main, "get_settings", lambda: settings)
    identity = GoogleIdentity(
        subject="google-subject-open",
        email=f"open-{time.time_ns()}@example.com",
        name="Open Redirect",
        email_verified=True,
    )
    monkeypatch.setattr(
        orchestrator_main, "exchange_code_for_identity", AsyncMock(return_value=identity)
    )
    for unsafe in ("https://evil.example", "//evil.example", "/api/v1/billing/checkout"):
        state = sign_payload(
            {"nonce": "n", "exp": int(time.time()) + 60, "next": unsafe}, SECRET
        )
        response = await client.get(
            "/api/v1/auth/google/callback",
            params={"code": "auth-code", "state": state},
            follow_redirects=False,
        )
        assert response.status_code == 307
        assert response.headers["location"] == "http://frontend.test/dashboard"


async def test_google_callback_rejects_bad_state(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(orchestrator_main, "get_settings", google_settings)
    response = await client.get(
        "/api/v1/auth/google/callback",
        params={"code": "auth-code", "state": "tampered"},
        follow_redirects=False,
    )
    assert response.status_code == 400
