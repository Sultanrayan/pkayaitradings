"""Tests for authentication: hashing, tokens, user store and endpoints."""

from __future__ import annotations

import time

import httpx
import pytest

from orchestrator import main as orchestrator_main
from orchestrator.auth import (
    AuthError,
    UserStore,
    create_token,
    decode_token,
    hash_password,
    verify_password,
)
from shared.config import Settings

SECRET = "test-secret"


def test_password_hash_round_trip() -> None:
    encoded = hash_password("supersecret")
    assert encoded.startswith("pbkdf2_sha256$")
    assert verify_password("supersecret", encoded) is True
    assert verify_password("wrongpassword", encoded) is False


def test_password_too_short_rejected() -> None:
    with pytest.raises(AuthError):
        hash_password("short")


def test_verify_password_handles_malformed_hash() -> None:
    assert verify_password("x", "not-a-valid-hash") is False


def test_token_round_trip() -> None:
    store = UserStore()
    user = store.register("Ada", "ada@example.com", "supersecret")
    token = create_token(user, SECRET, ttl_seconds=60)
    payload = decode_token(token, SECRET)
    assert payload["sub"] == user.id
    assert payload["email"] == "ada@example.com"


def test_token_rejects_tampering_and_expiry() -> None:
    store = UserStore()
    user = store.register("Ada", "ada2@example.com", "supersecret")
    token = create_token(user, SECRET, ttl_seconds=60)
    body, signature = token.split(".")
    # Flip the last base64 character to a guaranteed-different one; hardcoding
    # "x" made this test flaky whenever the signature already ended in "x".
    tampered_char = "A" if signature[-1] != "A" else "B"
    with pytest.raises(AuthError):
        decode_token(f"{body}.{signature[:-1]}{tampered_char}", SECRET)
    with pytest.raises(AuthError):
        decode_token("garbage", SECRET)

    expired = create_token(user, SECRET, ttl_seconds=-1)
    with pytest.raises(AuthError):
        decode_token(expired, SECRET)


def test_user_store_register_and_authenticate() -> None:
    store = UserStore()
    user = store.register("Ada", "Ada@Example.com", "supersecret")
    assert user.email == "ada@example.com"
    assert store.size == 1
    assert store.authenticate("ada@example.com", "supersecret") is not None
    assert store.authenticate("ada@example.com", "nope") is None
    assert store.authenticate("missing@example.com", "x") is None
    assert store.get(user.id) == user
    with pytest.raises(AuthError):
        store.register("Dup", "ada@example.com", "supersecret")


@pytest.fixture
async def client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=orchestrator_main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client


async def test_register_login_me_flow(client: httpx.AsyncClient) -> None:
    email = f"flow-{time.time_ns()}@example.com"
    register = await client.post(
        "/api/v1/auth/register",
        json={"name": "Flow User", "email": email, "password": "supersecret"},
    )
    assert register.status_code == 201
    body = register.json()
    assert body["user"]["email"] == email
    token = body["token"]

    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == email

    login = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "supersecret"}
    )
    assert login.status_code == 200
    assert login.json()["token"]


async def test_register_rejects_bad_email(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/register",
        json={"name": "Bad", "email": "not-an-email", "password": "supersecret"},
    )
    assert response.status_code == 422


async def test_register_rejects_short_password(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/register",
        json={"name": "Bad", "email": "short@example.com", "password": "123"},
    )
    assert response.status_code == 422


async def test_login_rejects_wrong_password(client: httpx.AsyncClient) -> None:
    email = f"wrong-{time.time_ns()}@example.com"
    await client.post(
        "/api/v1/auth/register",
        json={"name": "User", "email": email, "password": "supersecret"},
    )
    response = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "wrongpassword"}
    )
    assert response.status_code == 401


async def test_me_requires_token(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401


async def test_me_rejects_invalid_token(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not.a.token"})
    assert response.status_code == 401


async def test_middleware_enforces_auth_when_enabled(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        orchestrator_main,
        "get_settings",
        lambda: Settings(auth_required=True, auth_secret=SECRET),
    )
    protected = await client.get("/api/v1/signals")
    assert protected.status_code == 401

    health = await client.get("/health")
    assert health.status_code == 200
