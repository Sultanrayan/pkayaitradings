"""Tests for the developer access-request workflow and the admin allowlist."""

from __future__ import annotations

import time

import httpx
import pytest

from orchestrator import main as orchestrator_main

ADMIN_EMAIL = "menmengleapx1@gmail.com"


@pytest.fixture
async def client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=orchestrator_main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client


async def _auth_token(client: httpx.AsyncClient, email: str) -> str:
    """Register or sign in and return the session token."""
    register = await client.post(
        "/api/v1/auth/register",
        json={"name": "Applicant", "email": email, "password": "supersecret"},
    )
    if register.status_code == 400:  # already registered by an earlier test
        login = await client.post(
            "/api/v1/auth/login", json={"email": email, "password": "supersecret"}
        )
        assert login.status_code == 200
        token = login.json()["token"]
    else:
        assert register.status_code == 201
        token = register.json()["token"]

    return token


async def test_apply_for_access_is_public_and_returns_review_message(
    client: httpx.AsyncClient,
) -> None:
    response = await client.post(
        "/api/v1/access/apply",
        json={
            "name": "Dev Applicant",
            "email": f"dev-{time.time_ns()}@example.com",
            "use_case": "I want to backtest the agent strategies on my own candles.",
            "website": "https://example.com",
        },
    )
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "received"
    assert "Thank you" in body["message"]
    assert "24 to 48 hours" in body["message"]


async def test_apply_rejects_invalid_email(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/v1/access/apply",
        json={"name": "Bad", "email": "not-an-email", "use_case": "Testing", "website": ""},
    )
    assert response.status_code == 422


async def test_non_admin_is_rejected(client: httpx.AsyncClient) -> None:
    token = await _auth_token(client, f"user-{time.time_ns()}@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    session = await client.get("/api/v1/admin/session", headers=headers)
    assert session.status_code == 403
    requests = await client.get("/api/v1/admin/requests", headers=headers)
    assert requests.status_code == 403


async def test_non_allowlisted_admin_is_rejected(client: httpx.AsyncClient) -> None:
    token = await _auth_token(client, f"non-admin-{time.time_ns()}@example.com")
    response = await client.get(
        "/api/v1/admin/session", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 403
    assert "not authorized" in response.json()["detail"].lower()


async def test_admin_can_list_and_approve_requests(client: httpx.AsyncClient) -> None:
    applicant = f"approved-{time.time_ns()}@example.com"
    created = await client.post(
        "/api/v1/access/apply",
        json={
            "name": "Approved Dev",
            "email": applicant,
            "use_case": "Building a research dashboard on top of the agent signals.",
            "website": "https://approved.example.com",
        },
    )
    request_id = created.json()["id"]

    admin_token = await _auth_token(client, ADMIN_EMAIL)
    headers = {"Authorization": f"Bearer {admin_token}"}

    session = await client.get("/api/v1/admin/session", headers=headers)
    assert session.status_code == 200
    assert session.json()["admin"] is True

    listed = await client.get("/api/v1/admin/requests", headers=headers)
    assert listed.status_code == 200
    assert request_id in {item["id"] for item in listed.json()}

    approved = await client.post(f"/api/v1/admin/requests/{request_id}/approve", headers=headers)
    assert approved.status_code == 200
    body = approved.json()
    assert body["status"] == "approved"
    assert body["token"]


async def test_admin_endpoints_require_token(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/admin/requests")
    assert response.status_code == 401


async def test_admin_can_list_users_and_stats(client: httpx.AsyncClient) -> None:
    admin_token = await _auth_token(client, ADMIN_EMAIL)
    headers = {"Authorization": f"Bearer {admin_token}"}

    users = await client.get("/api/v1/admin/users", headers=headers)
    assert users.status_code == 200
    emails = [user["email"] for user in users.json()]
    assert ADMIN_EMAIL in emails

    stats = await client.get("/api/v1/admin/stats", headers=headers)
    assert stats.status_code == 200
    body = stats.json()
    assert body["total_users"] == len(users.json())
    assert "free" in body["users_by_plan"]
    assert body["total_analyses"] >= 0
    assert body["pending_requests"] >= 0


async def test_admin_can_list_billing(client: httpx.AsyncClient) -> None:
    admin_token = await _auth_token(client, ADMIN_EMAIL)
    headers = {"Authorization": f"Bearer {admin_token}"}
    response = await client.get("/api/v1/admin/billing", headers=headers)
    assert response.status_code == 200
    assert isinstance(response.json(), list)


async def test_non_admin_rejected_from_new_endpoints(client: httpx.AsyncClient) -> None:
    token = await _auth_token(client, f"unauth-{time.time_ns()}@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    for path in ("/api/v1/admin/users", "/api/v1/admin/stats", "/api/v1/admin/billing"):
        response = await client.get(path, headers=headers)
        assert response.status_code == 403
