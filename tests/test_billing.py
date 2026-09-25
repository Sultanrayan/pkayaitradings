"""Tests for billing: KHQR checkout, verification, webhook and plan activation."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from dataclasses import replace

import httpx
import pytest
from fastapi import FastAPI

from orchestrator import main as orchestrator_main
from orchestrator.billing import BillingPayment, BillingStore
from shared.config import Settings
from tests.test_pipeline import _build_pipeline
from tests.test_strategy import make_series


class _StubKhpay:
    """Fake Khpay client returning a fixed payment + configurable check result."""

    def __init__(self, *, paid: bool = False) -> None:
        self._paid = paid
        self.created: list[dict[str, object]] = []

    async def create_payment(
        self,
        *,
        amount: float,
        currency: str = "USD",
        note: str | None = None,
        callback_url: str | None = None,
        client_id: str | None = None,
    ) -> dict[str, object]:
        self.created.append({"amount": amount, "client_id": client_id})
        return {
            "transaction_id": "txn_test0000000001",
            "qr_image": "data:image/png;base64,QUFBQQ==",
            "qr_string": "000201...KHQR",
            "payment_url": "https://khpay.site/pay/txn_test0000000001",
        }

    async def check_payment(self, transaction_id: str) -> dict[str, object]:
        return {
            "transaction_id": transaction_id,
            "paid": self._paid,
            "status": "paid" if self._paid else "pending",
            "amount": "15.00",
            "currency": "USD",
        }


@pytest.fixture
def configured_app(settings: Settings) -> FastAPI:
    pipeline = _build_pipeline(settings, make_series(300, drift=0.6))
    orchestrator_main.app.state.pipeline = pipeline
    orchestrator_main.app.state.settings = settings
    return orchestrator_main.app


@pytest.fixture
async def client(
    configured_app: FastAPI,
) -> AsyncGenerator[httpx.AsyncClient, None]:
    transport = httpx.ASGITransport(app=configured_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client


async def _register(client: httpx.AsyncClient, email: str) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/register",
        json={"name": "Billing", "email": email, "password": "supersecret"},
    )
    if response.status_code == 400:
        response = await client.post(
            "/api/v1/auth/login", json={"email": email, "password": "supersecret"}
        )
    assert response.status_code in {201, 200}
    token = response.json()["token"]
    return {"Authorization": f"Bearer {token}"}


async def test_checkout_returns_khqr(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub = _StubKhpay()
    monkeypatch.setattr(orchestrator_main, "_khpay_client", lambda settings: stub)
    headers = await _register(client, "checkout@example.com")

    response = await client.post("/api/v1/billing/checkout", json={"plan": "pro"}, headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["plan"] == "pro"
    assert body["amount"] == pytest.approx(15.0)
    assert body["payment_id"] == "txn_test0000000001"
    assert body["qr_image"].startswith("data:image/png")
    assert body["qr_string"]


async def test_checkout_requires_auth(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/v1/billing/checkout", json={"plan": "pro"})
    assert response.status_code == 401


async def test_checkout_rejects_unknown_plan(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(orchestrator_main, "_khpay_client", lambda settings: _StubKhpay())
    headers = await _register(client, "badplan@example.com")
    response = await client.post("/api/v1/billing/checkout", json={"plan": "enterprise"}, headers=headers)
    assert response.status_code == 422


async def test_verify_activates_plan_when_paid(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub = _StubKhpay(paid=True)
    monkeypatch.setattr(orchestrator_main, "_khpay_client", lambda settings: stub)
    headers = await _register(client, "paid@example.com")

    checkout = await client.post("/api/v1/billing/checkout", json={"plan": "pro"}, headers=headers)
    payment_id = checkout.json()["payment_id"]

    verify = await client.post(
        "/api/v1/billing/verify", json={"payment_id": payment_id}, headers=headers
    )
    assert verify.status_code == 200
    assert verify.json()["paid"] is True
    assert verify.json()["plan"] == "pro"

    plan = await client.get("/api/v1/billing/plan", headers=headers)
    assert plan.json()["plan"] == "pro"
    assert plan.json()["limit"] == 150


async def test_verify_pending_does_not_activate(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub = _StubKhpay(paid=False)
    monkeypatch.setattr(orchestrator_main, "_khpay_client", lambda settings: stub)
    headers = await _register(client, "pending@example.com")

    checkout = await client.post("/api/v1/billing/checkout", json={"plan": "ultra"}, headers=headers)
    payment_id = checkout.json()["payment_id"]

    verify = await client.post(
        "/api/v1/billing/verify", json={"payment_id": payment_id}, headers=headers
    )
    assert verify.json()["paid"] is False
    plan = await client.get("/api/v1/billing/plan", headers=headers)
    assert plan.json()["plan"] == "free"


async def test_webhook_activates_plan(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub = _StubKhpay(paid=True)
    monkeypatch.setattr(orchestrator_main, "_khpay_client", lambda settings: stub)
    headers = await _register(client, "webhook@example.com")

    checkout = await client.post("/api/v1/billing/checkout", json={"plan": "pro"}, headers=headers)
    payment_id = checkout.json()["payment_id"]

    webhook = await client.post(
        "/api/v1/billing/webhook",
        json={"event": "payment.paid", "data": {"transaction_id": payment_id}},
    )
    assert webhook.status_code == 200
    assert webhook.json()["ok"] is True

    plan = await client.get("/api/v1/billing/plan", headers=headers)
    assert plan.json()["plan"] == "pro"


async def test_trial_grants_pro_for_two_months(client: httpx.AsyncClient) -> None:
    headers = await _register(client, "trial@example.com")

    response = await client.post("/api/v1/billing/trial", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["plan"] == "pro"
    assert body["limit"] == 150
    assert body["remaining"] == 150

    plan = await client.get("/api/v1/billing/plan", headers=headers)
    assert plan.json()["plan"] == "pro"
    assert plan.json()["expires_at"] is not None


async def test_trial_requires_auth(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/v1/billing/trial")
    assert response.status_code == 401


async def test_analyze_blocked_when_quota_exhausted(
    client: httpx.AsyncClient,
) -> None:
    register = await client.post(
        "/api/v1/auth/register",
        json={"name": "Quota", "email": "quota-uid@example.com", "password": "supersecret"},
    )
    body = register.json()
    headers = {"Authorization": f"Bearer {body['token']}"}
    user = orchestrator_main._users.get(str(body["user"]["id"]))
    assert user is not None
    exhausted = replace(user, analysis_used=20)
    orchestrator_main._users.update(exhausted)

    response = await client.post("/api/v1/analyze/XAUUSD", headers=headers)
    assert response.status_code == 402
    assert "limit" in response.json()["detail"].lower()


async def test_analyze_allowed_with_remaining_quota(
    client: httpx.AsyncClient,
) -> None:
    headers = await _register(client, "allowed@example.com")
    response = await client.post("/api/v1/analyze/XAUUSD", headers=headers)
    assert response.status_code == 200


def test_billing_store_persistence(tmp_path: object) -> None:
    import pathlib

    path = pathlib.Path(str(tmp_path)) / "billing.json"
    store = BillingStore(path)
    store.create(BillingPayment(transaction_id="txn_a", user_id="u1", plan="pro", amount=15.0))
    reloaded = BillingStore(path)
    first = reloaded.get("txn_a")
    assert first is not None
    assert first.plan == "pro"
    reloaded.mark("txn_a", "paid")
    second = BillingStore(path).get("txn_a")
    assert second is not None
    assert second.status == "paid"
