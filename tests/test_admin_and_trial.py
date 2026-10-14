"""Tests for the retired Pro trial and the one-week migration rule."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from orchestrator import plans
from scripts.migrate_trial_pro_to_one_week import plan_migration

NOW = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)


# ------------------------------------------------------------- trial removed


def test_activate_trial_is_gone() -> None:
    assert not hasattr(plans, "activate_trial")


def test_plan_trial_days_setting_is_gone() -> None:
    from shared.config import Settings

    assert "plan_trial_days" not in Settings.model_fields


def test_billing_period_is_still_thirty_days() -> None:
    from shared.config import Settings

    assert Settings().plan_billing_period_days == 30


# ------------------------------------------------------------- migration rule


def _user(uid: str, email: str, plan: str, expiry: datetime | None) -> dict:
    return {
        "id": uid,
        "email": email,
        "plan": plan,
        "plan_expires_at": expiry.isoformat() if expiry else None,
    }


def _paid(uid: str) -> dict:
    return {"transaction_id": f"txn_{uid}", "user_id": uid, "plan": "pro", "amount": 13.0, "status": "paid"}


def _pending(uid: str) -> dict:
    return {"transaction_id": f"txn_{uid}", "user_id": uid, "plan": "pro", "amount": 13.0, "status": "pending"}


def test_trial_pro_is_shortened_to_one_week() -> None:
    users = [_user("u1", "trial@example.com", "pro", NOW + timedelta(days=60))]
    changed, skipped = plan_migration(users, [], now=NOW)
    assert len(changed) == 1
    assert not skipped
    assert changed[0]["to"] == (NOW + timedelta(days=7)).isoformat()


def test_paying_pro_is_untouched() -> None:
    users = [_user("u2", "paid@example.com", "pro", NOW + timedelta(days=25))]
    changed, skipped = plan_migration(users, [_paid("u2")], now=NOW)
    assert not changed
    assert skipped[0]["why"] == "paid"


def test_pending_payment_still_counts_as_free() -> None:
    """Per the agreed rule only a *paid* record exempts a user."""
    users = [_user("u3", "pending@example.com", "pro", NOW + timedelta(days=60))]
    changed, _ = plan_migration(users, [_pending("u3")], now=NOW)
    assert len(changed) == 1


def test_migration_never_extends_someone() -> None:
    users = [_user("u4", "soon@example.com", "pro", NOW + timedelta(days=1))]
    changed, skipped = plan_migration(users, [], now=NOW)
    assert not changed
    assert skipped[0]["why"] == "already within 7 days"


def test_non_pro_plans_are_ignored() -> None:
    users = [_user("u5", "free@example.com", "free", None)]
    changed, skipped = plan_migration(users, [], now=NOW)
    assert not changed
    assert not skipped


def test_already_expired_pro_is_left_to_the_service() -> None:
    users = [_user("u6", "lapsed@example.com", "pro", NOW - timedelta(days=1))]
    changed, skipped = plan_migration(users, [], now=NOW)
    assert not changed
    assert skipped[0]["why"] == "already expired"


def test_missing_expiry_is_reported_not_guessed() -> None:
    users = [_user("u7", "noexpiry@example.com", "pro", None)]
    changed, skipped = plan_migration(users, [], now=NOW)
    assert not changed
    assert skipped[0]["why"] == "no expiry set"


def test_unparseable_expiry_is_reported_not_guessed() -> None:
    users = [_user("u8", "bad@example.com", "pro", NOW)]
    users[0]["plan_expires_at"] = "not-a-date"
    changed, skipped = plan_migration(users, [], now=NOW)
    assert not changed
    assert skipped[0]["why"] == "unparseable expiry"


def test_a_paying_user_who_also_trialled_is_exempt() -> None:
    """The record says they paid, which is what protects their 30 days."""
    users = [_user("u9", "converted@example.com", "pro", NOW + timedelta(days=60))]
    changed, _ = plan_migration(users, [_paid("u9")], now=NOW)
    assert not changed


def test_mixed_population() -> None:
    users = [
        _user("a", "a@example.com", "pro", NOW + timedelta(days=60)),
        _user("b", "b@example.com", "pro", NOW + timedelta(days=60)),
        _user("c", "c@example.com", "free", None),
    ]
    changed, skipped = plan_migration(users, [_paid("b")], now=NOW)
    assert len(changed) == 1
    assert changed[0]["id"] == "a"
    assert skipped[0]["id"] == "b"


def test_inputs_are_not_mutated() -> None:
    users = [_user("u", "x@example.com", "pro", NOW + timedelta(days=60))]
    before = dict(users[0])
    plan_migration(users, [], now=NOW)
    assert users[0] == before


# ------------------------------------------------------------------- admin


def test_admin_allowlist_default() -> None:
    """The code default is the single new administrator.

    Read off the field rather than an instance: a developer ``.env`` may still carry
    ``ADMIN_EMAILS``, and this asserts what ships, not what is configured locally.
    """
    from shared.config import Settings

    field = Settings.model_fields["admin_emails"]
    assert field.default_factory() == ["superpkay@gmail.com"]


def test_admin_allowlist_parses_a_comma_list() -> None:
    from shared.config import Settings

    parsed = Settings(admin_emails="a@example.com, B@example.com ").admin_emails
    assert parsed == ["a@example.com", "b@example.com"]


# Clearing ADMIN_EMAILS must hand the console back to the built-in admin, not to
# nobody. Compose passes `ADMIN_EMAILS=${ADMIN_EMAILS:-}`, so a cleared variable
# arrives as an empty string; reading that as an empty allowlist locks every
# administrator out of /pkay-control-x7q9.


def test_blank_admin_emails_falls_back_to_the_default() -> None:
    from shared.config import Settings

    assert Settings(admin_emails="").admin_emails == ["superpkay@gmail.com"]


def test_whitespace_only_admin_emails_falls_back_to_the_default() -> None:
    from shared.config import Settings

    assert Settings(admin_emails="   ").admin_emails == ["superpkay@gmail.com"]


def test_empty_json_array_falls_back_to_the_default() -> None:
    from shared.config import Settings

    assert Settings(admin_emails="[]").admin_emails == ["superpkay@gmail.com"]


def test_separator_only_admin_emails_falls_back_to_the_default() -> None:
    from shared.config import Settings

    assert Settings(admin_emails=", ,").admin_emails == ["superpkay@gmail.com"]


def test_blank_admin_emails_env_var_does_not_empty_the_allowlist(monkeypatch) -> None:
    """The real production path: an empty ADMIN_EMAILS in the environment."""
    from shared.config import Settings

    monkeypatch.setenv("ADMIN_EMAILS", "")
    assert Settings().admin_emails == ["superpkay@gmail.com"]


def test_admin_emails_default_matches_the_module_constant() -> None:
    from shared.config import DEFAULT_ADMIN_EMAILS, Settings

    assert Settings.model_fields["admin_emails"].default_factory() == list(
        DEFAULT_ADMIN_EMAILS
    )


def test_previous_admins_are_not_in_the_default() -> None:
    from shared.config import Settings

    field = Settings.model_fields["admin_emails"]
    defaults = [e.lower() for e in field.default_factory()]
    assert "menmengleapx1@gmail.com" not in defaults
    assert "devlopercyberghost@gmail.com" not in defaults
    assert len(defaults) == 1


async def test_admin_gate_accepts_the_allowlisted_address() -> None:
    """Admin is an email allowlist over a normal login, not a separate password."""
    from httpx import ASGITransport, AsyncClient

    from orchestrator.auth import User
    from orchestrator.main import app, get_current_user, get_settings

    allowlisted = get_settings().admin_emails[0]
    user = User(
        id="adm1",
        name="Adm",
        email=allowlisted,
        password_hash=None,
        created_at=NOW,
        plan="free",
    )
    app.dependency_overrides[get_current_user] = lambda: user
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/admin/session")
    app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json()["admin"] is True


async def test_admin_gate_rejects_anyone_else() -> None:
    from httpx import ASGITransport, AsyncClient

    from orchestrator.auth import User
    from orchestrator.main import app, get_current_user

    user = User(
        id="u9",
        name="Not Admin",
        email="someone-else@example.com",
        password_hash=None,
        created_at=NOW,
        plan="free",
    )
    app.dependency_overrides[get_current_user] = lambda: user
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/admin/session")
    app.dependency_overrides.clear()
    assert response.status_code == 403


# ------------------------------------------------------------------- zenmux


def test_zenmux_endpoint_requires_a_user() -> None:
    import inspect

    from orchestrator.main import zenmux

    params = inspect.signature(zenmux).parameters
    assert "user" in params
    assert params["user"].annotation is not inspect.Parameter.empty


def test_zenmux_consumes_exactly_one_analysis() -> None:
    """A Zenmux card costs one analysis, the same unit the pricing page quotes."""
    from orchestrator.auth import User
    from shared.config import Settings

    account = User(
        id="z1",
        name="Z",
        email="z@example.com",
        password_hash=None,
        created_at=NOW,
        plan="free",
        analysis_period_start=NOW,
        analysis_day_start=NOW.replace(hour=0, minute=0, second=0, microsecond=0),
    )
    settings = Settings()
    result = plans.consume(account, settings, now=NOW)
    assert result.allowed is True
    assert result.user.analysis_used == 1
    assert result.user.analysis_used_today == 1


def test_zenmux_costs_exactly_one_from_the_daily_cap() -> None:
    """Free allows 2/day; two Zenmux cards should exhaust it and a third must fail."""
    from orchestrator.auth import User
    from shared.config import Settings

    account = User(
        id="z2",
        name="Z",
        email="z@example.com",
        password_hash=None,
        created_at=NOW,
        plan="free",
        analysis_period_start=NOW,
        analysis_day_start=NOW.replace(hour=0, minute=0, second=0, microsecond=0),
    )
    settings = Settings()
    first = plans.consume(account, settings, now=NOW)
    second = plans.consume(first.user, settings, now=NOW)
    third = plans.consume(second.user, settings, now=NOW)
    assert first.allowed and second.allowed
    assert third.allowed is False
    assert "Daily" in (third.reason or "")
