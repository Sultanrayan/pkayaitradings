"""Tests for the plan limits, usage accounting and auto-deactivation logic."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from orchestrator.auth import User
from orchestrator.plans import (
    activate,
    activate_trial,
    consume,
    consume_many,
    enforce,
    plan_limit,
    plan_price,
    status,
)
from shared.config import Settings


def make_user(**overrides: object) -> User:
    base = dict(
        id="u1",
        name="Ada",
        email="ada@example.com",
        password_hash=None,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    base.update(overrides)
    return User(**base)  # type: ignore[arg-type]


def make_settings(**overrides: object) -> Settings:
    base = dict(
        plan_free_monthly_limit=3,
        plan_pro_monthly_limit=10,
        plan_ultra_monthly_limit=-1,
        plan_billing_period_days=30,
    )
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


NOW = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)


def test_plan_limits_and_prices() -> None:
    settings = make_settings()
    assert plan_limit("free", settings) == 3
    assert plan_limit("pro", settings) == 10
    assert plan_limit("ultra", settings) == -1
    assert plan_price("pro", settings) == pytest.approx(15.0)
    assert plan_price("ultra", settings) == pytest.approx(65.0)
    assert plan_price("free", settings) is None


def test_expired_paid_plan_is_downgraded_to_free() -> None:
    settings = make_settings()
    user = make_user(
        plan="pro",
        plan_expires_at=NOW - timedelta(days=1),
        analysis_used=7,
        analysis_period_start=NOW - timedelta(days=20),
    )
    enforced = enforce(user, settings, now=NOW)
    assert enforced.plan == "free"
    assert enforced.plan_expires_at is None
    assert enforced.analysis_used == 0


def test_active_plan_not_downgraded() -> None:
    settings = make_settings()
    user = make_user(
        plan="pro",
        plan_expires_at=NOW + timedelta(days=10),
        analysis_used=4,
        analysis_period_start=NOW - timedelta(days=1),
    )
    enforced = enforce(user, settings, now=NOW)
    assert enforced.plan == "pro"


def test_period_rollover_resets_usage() -> None:
    settings = make_settings(plan_billing_period_days=30)
    user = make_user(
        plan="free",
        analysis_used=3,
        analysis_period_start=NOW - timedelta(days=61),
    )
    enforced = enforce(user, settings, now=NOW)
    assert enforced.analysis_used == 0
    assert enforced.analysis_period_start <= NOW


def test_consume_increments_until_limit() -> None:
    settings = make_settings(plan_free_monthly_limit=2)
    user = make_user(analysis_period_start=NOW - timedelta(days=1))
    first = consume(user, settings, now=NOW)
    assert first.allowed is True
    assert first.user.analysis_used == 1
    second = consume(first.user, settings, now=NOW)
    assert second.allowed is True
    assert second.user.analysis_used == 2
    third = consume(second.user, settings, now=NOW)
    assert third.allowed is False
    assert third.user.analysis_used == 2
    assert "limit" in (third.reason or "").lower()


def test_consume_many_batch() -> None:
    settings = make_settings(plan_free_monthly_limit=3)
    user = make_user(analysis_period_start=NOW - timedelta(days=1))
    result = consume_many(user, settings, count=3, now=NOW)
    assert result.allowed is True
    assert result.user.analysis_used == 3
    over = consume_many(result.user, settings, count=1, now=NOW)
    assert over.allowed is False


def test_ultra_is_unlimited() -> None:
    settings = make_settings()
    user = make_user(
        plan="ultra",
        plan_expires_at=NOW + timedelta(days=20),
        analysis_used=999_999,
        analysis_period_start=NOW - timedelta(days=1),
    )
    result = consume(user, settings, now=NOW)
    assert result.allowed is True
    assert result.user.analysis_used == 1_000_000


def test_activate_sets_plan_and_expiry() -> None:
    settings = make_settings(plan_billing_period_days=30)
    user = make_user(analysis_used=3, analysis_period_start=NOW - timedelta(days=5))
    activated = activate(user, "pro", settings, now=NOW)
    assert activated.plan == "pro"
    assert activated.plan_expires_at == NOW + timedelta(days=30)
    assert activated.analysis_used == 0
    assert activated.analysis_period_start == NOW


def test_activate_rejects_invalid_plan() -> None:
    settings = make_settings()
    with pytest.raises(ValueError, match="Not a purchasable plan"):
        activate(make_user(), "enterprise", settings)


def test_trial_grants_pro_for_two_months() -> None:
    settings = make_settings(plan_trial_days=60)
    user = make_user(analysis_used=3, analysis_period_start=NOW - timedelta(days=5))
    updated, granted = activate_trial(user, settings, now=NOW)
    assert granted is True
    assert updated.plan == "pro"
    assert updated.plan_expires_at == NOW + timedelta(days=60)
    assert updated.analysis_used == 0
    assert updated.analysis_period_start == NOW


def test_trial_does_not_rerun_when_entitled() -> None:
    settings = make_settings(plan_trial_days=60)
    user = make_user(
        plan="pro",
        plan_expires_at=NOW + timedelta(days=10),
        analysis_used=5,
        analysis_period_start=NOW - timedelta(days=1),
    )
    updated, granted = activate_trial(user, settings, now=NOW)
    assert granted is False
    assert updated is user


def test_status_reports_remaining_and_unlimited() -> None:
    settings = make_settings(plan_free_monthly_limit=3)
    user = make_user(analysis_used=1, analysis_period_start=NOW - timedelta(days=1))
    info = status(user, settings, now=NOW)
    assert info.plan == "free"
    assert info.used == 1
    assert info.remaining == 2
    assert info.active is True

    ultra = make_user(
        plan="ultra",
        plan_expires_at=NOW + timedelta(days=10),
        analysis_used=5,
        analysis_period_start=NOW,
    )
    ultra_info = status(ultra, settings, now=NOW)
    assert ultra_info.remaining == -1
    assert ultra_info.price_usd == pytest.approx(65.0)