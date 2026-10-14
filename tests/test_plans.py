"""Tests for the plan limits, usage accounting and auto-deactivation logic."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from orchestrator.auth import User
from orchestrator.plans import (
    activate,
    consume,
    consume_many,
    enforce,
    plan_daily_limit,
    plan_limit,
    plan_price,
    status,
)
from shared.config import Settings


def make_user(**overrides: object) -> User:
    base = {
        "id": "u1",
        "name": "Ada",
        "email": "ada@example.com",
        "password_hash": None,
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
    }
    base.update(overrides)
    return User(**base)  # type: ignore[arg-type]


def make_settings(**overrides: object) -> Settings:
    base = {
        "plan_free_daily_limit": 3,
        "plan_free_monthly_limit": 3,
        "plan_starter_daily_limit": 8,
        "plan_starter_monthly_limit": 240,
        "plan_pro_daily_limit": 20,
        "plan_pro_monthly_limit": 10,
        "plan_ultra_daily_limit": 250,
        "plan_ultra_monthly_limit": -1,
        "plan_starter_price_usd": 6.0,
        "plan_pro_price_usd": 13.0,
        "plan_ultra_price_usd": 250.0,
        "plan_billing_period_days": 30,
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


NOW = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
MIDNIGHT = datetime(2026, 9, 1, 0, 0, tzinfo=UTC)


def test_plan_limits_and_prices() -> None:
    settings = make_settings()
    assert plan_limit("free", settings) == 3
    assert plan_limit("starter", settings) == 240
    assert plan_limit("pro", settings) == 10
    assert plan_limit("ultra", settings) == -1
    assert plan_price("starter", settings) == pytest.approx(6.0)
    assert plan_price("pro", settings) == pytest.approx(13.0)
    assert plan_price("ultra", settings) == pytest.approx(250.0)
    assert plan_price("free", settings) is None


def test_plan_daily_limits() -> None:
    settings = make_settings()
    assert plan_daily_limit("free", settings) == 3
    assert plan_daily_limit("starter", settings) == 8
    assert plan_daily_limit("pro", settings) == 20
    assert plan_daily_limit("ultra", settings) == 250


def test_shipped_defaults_match_published_pricing() -> None:
    """The defaults in `shared/config.py` are what the pricing page advertises."""
    settings = Settings()
    assert (settings.plan_free_daily_limit, settings.plan_free_monthly_limit) == (2, 60)
    assert (settings.plan_starter_daily_limit, settings.plan_starter_monthly_limit) == (8, 240)
    assert (settings.plan_pro_daily_limit, settings.plan_pro_monthly_limit) == (20, 600)
    assert (settings.plan_ultra_daily_limit, settings.plan_ultra_monthly_limit) == (250, 7500)
    assert settings.plan_starter_price_usd == pytest.approx(6.0)
    assert settings.plan_pro_price_usd == pytest.approx(13.0)
    assert settings.plan_ultra_price_usd == pytest.approx(250.0)


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


def test_expired_starter_plan_is_downgraded_to_free() -> None:
    settings = make_settings()
    user = make_user(
        plan="starter",
        plan_expires_at=NOW - timedelta(minutes=1),
        analysis_used=2,
    )
    enforced = enforce(user, settings, now=NOW)
    assert enforced.plan == "free"
    assert enforced.plan_expires_at is None


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
    settings = make_settings(plan_free_daily_limit=-1, plan_free_monthly_limit=2)
    user = make_user(analysis_period_start=NOW - timedelta(days=1), analysis_day_start=MIDNIGHT)
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
    settings = make_settings(plan_free_daily_limit=-1, plan_free_monthly_limit=3)
    user = make_user(analysis_period_start=NOW - timedelta(days=1), analysis_day_start=MIDNIGHT)
    result = consume_many(user, settings, count=3, now=NOW)
    assert result.allowed is True
    assert result.user.analysis_used == 3
    over = consume_many(result.user, settings, count=1, now=NOW)
    assert over.allowed is False


# ------------------------------------------------------------------ daily caps


def test_daily_cap_stops_consumption_before_monthly() -> None:
    settings = make_settings(plan_free_daily_limit=2, plan_free_monthly_limit=100)
    user = make_user(analysis_period_start=NOW, analysis_day_start=MIDNIGHT)
    first = consume(user, settings, now=NOW)
    second = consume(first.user, settings, now=NOW)
    third = consume(second.user, settings, now=NOW)
    assert first.allowed and second.allowed
    assert third.allowed is False
    assert "Daily" in (third.reason or "")
    # The monthly budget is untouched, so the refusal is purely the daily cap.
    assert third.user.analysis_used == 2
    assert third.user.analysis_used_today == 2


def test_daily_cap_resets_at_utc_midnight() -> None:
    settings = make_settings(plan_free_daily_limit=1, plan_free_monthly_limit=100)
    user = make_user(analysis_period_start=NOW, analysis_day_start=MIDNIGHT)
    first = consume(user, settings, now=NOW)
    assert first.allowed is True
    blocked = consume(first.user, settings, now=NOW)
    assert blocked.allowed is False

    next_day = datetime(2026, 9, 2, 9, 0, tzinfo=UTC)
    after_reset = consume(first.user, settings, now=next_day)
    assert after_reset.allowed is True
    assert after_reset.user.analysis_used_today == 1
    # The monthly counter keeps accumulating across the day boundary.
    assert after_reset.user.analysis_used == 2


def test_daily_counter_not_reset_within_the_same_day() -> None:
    settings = make_settings(plan_free_daily_limit=5)
    user = make_user(analysis_used_today=4, analysis_day_start=MIDNIGHT)
    evening = datetime(2026, 9, 1, 23, 30, tzinfo=UTC)
    enforced = enforce(user, settings, now=evening)
    assert enforced.analysis_used_today == 4


def test_stale_day_counter_from_before_the_field_existed_resets() -> None:
    """Records written before daily caps existed must not lock a user out."""
    settings = make_settings(plan_free_daily_limit=2, plan_free_monthly_limit=100)
    user = make_user(
        analysis_used_today=0,
        analysis_day_start=datetime(2020, 1, 1, tzinfo=UTC),
        analysis_period_start=datetime(2020, 1, 1, tzinfo=UTC),
    )
    enforced = enforce(user, settings, now=NOW)
    assert enforced.analysis_day_start == MIDNIGHT
    assert consume(enforced, settings, now=NOW).allowed is True


def test_status_reports_both_quotas() -> None:
    settings = make_settings(plan_free_daily_limit=3, plan_free_monthly_limit=10)
    user = make_user(
        analysis_used=1,
        analysis_used_today=2,
        analysis_period_start=NOW - timedelta(days=1),
        analysis_day_start=MIDNIGHT,
    )
    info = status(user, settings, now=NOW)
    assert info.plan == "free"
    assert info.used == 1
    assert info.remaining == 9
    assert info.used_today == 2
    assert info.remaining_today == 1
    assert info.daily_limit == 3
    assert info.active is True

    ultra = make_user(
        plan="ultra",
        plan_expires_at=NOW + timedelta(days=10),
        analysis_used=5,
        analysis_used_today=2,
        analysis_period_start=NOW,
        analysis_day_start=MIDNIGHT,
    )
    ultra_info = status(ultra, settings, now=NOW)
    assert ultra_info.remaining == -1
    assert ultra_info.price_usd == pytest.approx(250.0)


# ----------------------------------------------------------------- unlimited


def test_ultra_is_unlimited_on_both_caps() -> None:
    settings = make_settings(plan_ultra_daily_limit=-1, plan_ultra_monthly_limit=-1)
    user = make_user(
        plan="ultra",
        plan_expires_at=NOW + timedelta(days=20),
        analysis_used=999_999,
        analysis_used_today=999_999,
        analysis_period_start=NOW - timedelta(days=1),
        analysis_day_start=MIDNIGHT,
    )
    result = consume(user, settings, now=NOW)
    assert result.allowed is True
    assert result.user.analysis_used == 1_000_000
    assert result.user.analysis_used_today == 1_000_000


def test_shipped_ultra_is_capped_not_unlimited() -> None:
    """Ultra moved from unlimited to 250/day, so the cap must actually bite."""
    settings = Settings()
    user = make_user(
        plan="ultra",
        plan_expires_at=NOW + timedelta(days=20),
        analysis_used=7499,
        analysis_used_today=249,
        analysis_period_start=NOW,
        analysis_day_start=MIDNIGHT,
    )
    assert consume(user, settings, now=NOW).allowed is True
    over_day = consume(
        make_user(
            plan="ultra",
            plan_expires_at=NOW + timedelta(days=20),
            analysis_used=7499,
            analysis_used_today=250,
            analysis_period_start=NOW,
            analysis_day_start=MIDNIGHT,
        ),
        settings,
        now=NOW,
    )
    assert over_day.allowed is False
    assert "Daily" in (over_day.reason or "")


# ------------------------------------------------------------------ activation


def test_activate_sets_plan_and_expiry() -> None:
    settings = make_settings(plan_billing_period_days=30)
    user = make_user(analysis_used=3, analysis_period_start=NOW - timedelta(days=5))
    activated = activate(user, "pro", settings, now=NOW)
    assert activated.plan == "pro"
    assert activated.plan_expires_at == NOW + timedelta(days=30)
    assert activated.analysis_used == 0
    assert activated.analysis_period_start == NOW
    assert activated.analysis_used_today == 0


def test_activate_supports_starter() -> None:
    settings = make_settings(plan_billing_period_days=30)
    activated = activate(make_user(), "starter", settings, now=NOW)
    assert activated.plan == "starter"
    assert activated.plan_expires_at == NOW + timedelta(days=30)


def test_activate_rejects_invalid_plan() -> None:
    settings = make_settings()
    with pytest.raises(ValueError, match="Not a purchasable plan"):
        activate(make_user(), "enterprise", settings)


def test_activate_rejects_free() -> None:
    settings = make_settings()
    with pytest.raises(ValueError, match="Not a purchasable plan"):
        activate(make_user(), "free", settings)


def test_no_trial_offer_remains() -> None:
    """The free two-month Pro trial was discontinued.

    Nothing may reintroduce a way to grant it: the helper is gone, the setting is
    gone, and the endpoint answers 410 Gone.
    """
    from orchestrator import plans as plans_module
    from shared.config import Settings

    assert not hasattr(plans_module, "activate_trial")
    assert "plan_trial_days" not in Settings.model_fields


def test_valid_plans_includes_starter() -> None:
    from orchestrator.plans import PAID_PLANS, VALID_PLANS

    assert VALID_PLANS == ("free", "starter", "pro", "ultra")
    assert PAID_PLANS == ("starter", "pro", "ultra")
