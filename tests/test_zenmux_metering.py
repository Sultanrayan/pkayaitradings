"""Metering for ``POST /api/v1/zenmux``.

This endpoint shipped broken and nothing noticed, because the failure only
appeared once a working ``ZENMUX_API_KEY`` reached the server: the call site read

    plans.consume(user, get_settings(), count=1)

and ``consume`` has no ``count`` parameter, so every request that got far enough to
meter raised ``TypeError`` -> 500 *after* the upstream model had already answered.
The unit tests all passed, because they exercised ``answer_zenmux`` directly and
never this endpoint.

So these tests drive the route itself, and cover the two properties that were
wrong independently of the signature: an over-quota caller must be refused before
the paid upstream call, and a caller whose upstream call fails must not be billed.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from orchestrator import main as orchestrator_main
from orchestrator import plans
from orchestrator.auth import UserStore
from orchestrator.plans import check, consume_many
from orchestrator.zenmux import (
    AnalysisReason,
    ZenmuxRequest,
    ZenmuxResponse,
    ZenmuxUnavailable,
)
from shared.config import Settings
from tests.test_pipeline import _build_pipeline
from tests.test_strategy import make_series


@pytest.fixture
def configured_app(settings: Settings) -> FastAPI:
    pipeline = _build_pipeline(settings, make_series(300, drift=0.6))
    orchestrator_main.app.state.pipeline = pipeline
    orchestrator_main.app.state.settings = settings
    return orchestrator_main.app


@pytest.fixture
async def client(configured_app: FastAPI) -> AsyncGenerator[httpx.AsyncClient, None]:
    transport = httpx.ASGITransport(app=configured_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _register(client: httpx.AsyncClient, email: str) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/register",
        json={"name": "Zen", "email": email, "password": "supersecret"},
    )
    if response.status_code == 400:
        response = await client.post(
            "/api/v1/auth/login", json={"email": email, "password": "supersecret"}
        )
    assert response.status_code in {201, 200}, response.text
    return {"Authorization": f"Bearer {response.json()['token']}"}


def _card() -> ZenmuxResponse:
    """A fully-populated card, so the route's response_model validation is exercised."""
    return ZenmuxResponse(
        model_name="Super Zenmux",
        model_description="Deep market analysis",
        symbol="XAUUSD",
        symbol_label="XAU/USD",
        timeframe="M5",
        model_timeframe="M5",
        direction="BULLISH",
        confidence=0.61,
        probability_up=0.61,
        probability_down=0.39,
        structure="Higher highs and higher lows",
        structure_detail="Sequence of upswings intact",
        close=4100.0,
        support=4080.0,
        resistance=4120.0,
        atr=12.5,
        rsi=58.0,
        reasons=[AnalysisReason(detail="Breakout held", source="analysis")],
        summary="Bullish continuation setup.",
        updated_at="2026-10-06T00:00:00+00:00",
        limited=False,
    )


class _Stub:
    """Stands in for answer_zenmux and records whether it was called."""

    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.calls = 0

    async def __call__(self, settings: Settings, client: Any, body: ZenmuxRequest) -> Any:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return _card()


def _usage(email: str) -> tuple[int, int]:
    # The store is a module-level singleton in orchestrator.main, not app.state.
    store: UserStore = orchestrator_main._users
    user = store.get_by_email(email)
    assert user is not None
    return user.analysis_used, user.analysis_used_today


# --------------------------------------------------------------- the route works


async def test_zenmux_route_succeeds_and_spends_one_analysis(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The 500 that shipped: this route had never been executed end to end."""
    stub = _Stub()
    monkeypatch.setattr(orchestrator_main, "answer_zenmux", stub)
    headers = await _register(client, "zenmux-ok@example.com")

    response = await client.post(
        "/api/v1/zenmux", json={"question": "What is the setup?"}, headers=headers
    )

    assert response.status_code == 200, response.text
    assert response.json()["direction"] == "BULLISH"
    assert stub.calls == 1
    monthly, daily = _usage("zenmux-ok@example.com")
    assert monthly == 1
    assert daily == 1


async def test_a_second_call_spends_a_second_analysis(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(orchestrator_main, "answer_zenmux", _Stub())
    headers = await _register(client, "zenmux-twice@example.com")

    for _ in range(2):
        response = await client.post(
            "/api/v1/zenmux", json={"question": "Setup?"}, headers=headers
        )
        assert response.status_code == 200, response.text

    assert _usage("zenmux-twice@example.com") == (2, 2)


# ------------------------------------------------- ordering: check before spend


async def test_over_quota_is_refused_without_calling_upstream(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A 402 must not cost an upstream call, which is real money."""
    stub = _Stub()
    monkeypatch.setattr(orchestrator_main, "answer_zenmux", stub)
    settings = orchestrator_main.app.state.settings
    email = "zenmux-over@example.com"
    headers = await _register(client, email)

    store: UserStore = orchestrator_main._users
    user = store.get_by_email(email)
    assert user is not None
    daily_limit = plans.plan_daily_limit("free", settings)
    # Exactly at the cap: the next request has nothing left.
    store.update(
        consume_many(user, settings, count=daily_limit).user
    )

    response = await client.post(
        "/api/v1/zenmux", json={"question": "Setup?"}, headers=headers
    )

    assert response.status_code == 402, response.text
    assert "limit" in response.json()["detail"].lower()
    assert stub.calls == 0, "upstream was called for a caller who was over quota"
    assert _usage(email) == (daily_limit, daily_limit), "usage moved despite the refusal"


# --------------------------------------------------- billing: failures are free


async def test_upstream_failure_is_503_and_costs_nothing(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub = _Stub(error=ZenmuxUnavailable("upstream exploded"))
    monkeypatch.setattr(orchestrator_main, "answer_zenmux", stub)
    email = "zenmux-503@example.com"
    headers = await _register(client, email)

    response = await client.post(
        "/api/v1/zenmux", json={"question": "Setup?"}, headers=headers
    )

    assert response.status_code == 503, response.text
    assert stub.calls == 1
    assert _usage(email) == (0, 0), "a failed analysis was billed"


async def test_unconfigured_upstream_is_503_and_costs_nothing(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub = _Stub(
        error=ZenmuxUnavailable("Zenmux is not configured: ZENMUX_API_KEY is not set.")
    )
    monkeypatch.setattr(orchestrator_main, "answer_zenmux", stub)
    email = "zenmux-unset@example.com"
    headers = await _register(client, email)

    response = await client.post(
        "/api/v1/zenmux", json={"question": "Setup?"}, headers=headers
    )

    assert response.status_code == 503, response.text
    assert _usage(email) == (0, 0)


# ------------------------------------------------------------- plans.check()


def _user(settings: Settings, **overrides: Any) -> Any:
    from datetime import UTC, datetime

    from orchestrator.auth import User

    base: dict[str, Any] = {
        "id": "u1",
        "name": "U",
        "email": "u@example.com",
        "password_hash": None,
        "created_at": datetime.now(UTC),
    }
    base.update(overrides)
    return User(**base)


def test_check_spends_nothing(settings: Settings) -> None:
    user = _user(settings)
    result = check(user, settings)
    assert result.allowed is True
    assert result.reason is None
    assert result.user.analysis_used == 0
    assert result.user.analysis_used_today == 0


def test_check_and_consume_many_agree_on_the_daily_cap(settings: Settings) -> None:
    limit = plans.plan_daily_limit("free", settings)
    user = _user(settings, analysis_used_today=limit, analysis_used=limit)
    assert check(user, settings).allowed is False
    assert consume_many(user, settings, count=1).allowed is False


def test_check_and_consume_many_agree_on_the_monthly_cap(settings: Settings) -> None:
    limit = plans.plan_limit("free", settings)
    user = _user(settings, analysis_used=limit, analysis_used_today=0)
    assert check(user, settings).allowed is False
    assert consume_many(user, settings, count=1).allowed is False


def test_check_reports_the_same_reason_as_consume(settings: Settings) -> None:
    limit = plans.plan_daily_limit("free", settings)
    user = _user(settings, analysis_used_today=limit)
    assert check(user, settings).reason == consume_many(user, settings, count=1).reason


def test_check_allows_when_consume_would_allow(settings: Settings) -> None:
    user = _user(settings)
    assert check(user, settings).allowed == consume_many(user, settings, count=1).allowed


def test_check_rejects_a_negative_count(settings: Settings) -> None:
    with pytest.raises(ValueError, match="count must be >= 0"):
        check(_user(settings), settings, count=-1)
