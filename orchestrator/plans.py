"""User plan limits, usage accounting and billing-period logic.

Plans (no Enterprise):

* **Free**    — 2 analyses/day, 60 per billing period (USD 0)
* **Starter** — 8 analyses/day, 240 per billing period (USD 6)
* **Pro**     — 20 analyses/day, 600 per billing period (USD 13)
* **Ultra**   — 250 analyses/day, 7,500 per billing period (USD 250)

Every plan carries two independent caps and **both** are enforced: a daily cap that
resets at 00:00 UTC, and a cap per billing period (``plan_billing_period_days``). A
request is refused when either is reached, and the refusal names which one, because
"come back tomorrow" and "wait for the next period" are different instructions.

A paid plan is active until ``plan_expires_at``; once that moment passes the user is
automatically downgraded to Free. Usage resets at each period boundary for every user.
Functions are pure — they never touch persistence — so the API layer decides when to
save.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta

from orchestrator.auth import User
from shared.config import Settings

VALID_PLANS = ("free", "starter", "pro", "ultra")

#: Plans a user can buy. Free is not purchasable.
PAID_PLANS = ("starter", "pro", "ultra")


@dataclass(frozen=True)
class PlanStatus:
    """The user's plan and remaining usage for the current day and period."""

    plan: str
    limit: int
    used: int
    remaining: int
    daily_limit: int
    used_today: int
    remaining_today: int
    expires_at: datetime | None
    active: bool
    price_usd: float | None


@dataclass(frozen=True)
class ConsumeResult:
    """Outcome of consuming one analysis against a user's quota."""

    user: User
    allowed: bool
    reason: str | None


def plan_limit(plan: str, settings: Settings) -> int:
    """Return the analyses-per-period limit for ``plan`` (``-1`` = unlimited)."""
    return {
        "free": settings.plan_free_monthly_limit,
        "starter": settings.plan_starter_monthly_limit,
        "pro": settings.plan_pro_monthly_limit,
        "ultra": settings.plan_ultra_monthly_limit,
    }[plan]


def plan_daily_limit(plan: str, settings: Settings) -> int:
    """Return the analyses-per-UTC-day limit for ``plan`` (``-1`` = unlimited)."""
    return {
        "free": settings.plan_free_daily_limit,
        "starter": settings.plan_starter_daily_limit,
        "pro": settings.plan_pro_daily_limit,
        "ultra": settings.plan_ultra_daily_limit,
    }[plan]


def plan_price(plan: str, settings: Settings) -> float | None:
    """Return the USD price for a purchasable plan, else ``None``."""
    return {
        "starter": settings.plan_starter_price_usd,
        "pro": settings.plan_pro_price_usd,
        "ultra": settings.plan_ultra_price_usd,
    }.get(plan)


def enforce(user: User, settings: Settings, *, now: datetime | None = None) -> User:
    """Downgrade expired plans and roll both usage windows forward.

    Returns a new :class:`User` with the enforced state applied; the caller
    persists it when it differs from ``user``.
    """
    now = now or datetime.now(UTC)

    if user.plan in PAID_PLANS and user.plan_expires_at is not None and user.plan_expires_at <= now:
        user = replace(
            user,
            plan="free",
            plan_expires_at=None,
            analysis_used=0,
            analysis_used_today=0,
            analysis_period_start=now,
            analysis_day_start=_utc_midnight(now),
        )

    period_start = _advance_period(user.analysis_period_start, settings, now)
    if period_start != user.analysis_period_start:
        user = replace(user, analysis_period_start=period_start, analysis_used=0)

    day_start = _utc_midnight(user.analysis_day_start)
    today = _utc_midnight(now)
    if day_start < today:
        user = replace(user, analysis_day_start=today, analysis_used_today=0)
    return user


def consume(user: User, settings: Settings, *, now: datetime | None = None) -> ConsumeResult:
    """Enforce the plan, then reserve one analysis if either quota allows it."""
    return consume_many(user, settings, count=1, now=now)


def _quota_refusal(
    user: User, settings: Settings, count: int
) -> str | None:
    """Return why ``count`` analyses would be refused, or ``None`` if they are allowed.

    The daily cap is checked first because it is the tighter of the two in every
    plan, and because its remedy is sooner. Assumes ``user`` has been enforced.
    """
    daily_limit = plan_daily_limit(user.plan, settings)
    if daily_limit != -1 and user.analysis_used_today + count > daily_limit:
        return f"Daily analysis limit ({daily_limit}) reached"

    limit = plan_limit(user.plan, settings)
    if limit != -1 and user.analysis_used + count > limit:
        return f"Monthly analysis limit ({limit}) reached"

    return None


def check(
    user: User, settings: Settings, *, count: int = 1, now: datetime | None = None
) -> ConsumeResult:
    """Decide whether ``count`` analyses would be allowed, spending nothing.

    For endpoints that must not bill a caller when the work fails downstream: check
    first so an over-quota caller is refused before any paid call is made, then
    :func:`consume` once the result is actually in hand. The two share
    :func:`_quota_refusal`, so they cannot disagree about who is over quota.
    """
    if count < 0:
        raise ValueError("count must be >= 0")
    now = now or datetime.now(UTC)
    user = enforce(user, settings, now=now)
    reason = _quota_refusal(user, settings, count)
    return ConsumeResult(user=user, allowed=reason is None, reason=reason)


def consume_many(
    user: User, settings: Settings, *, count: int, now: datetime | None = None
) -> ConsumeResult:
    """Enforce the plan, then reserve ``count`` analyses if either quota allows."""
    if count < 0:
        raise ValueError("count must be >= 0")
    now = now or datetime.now(UTC)
    user = enforce(user, settings, now=now)

    reason = _quota_refusal(user, settings, count)
    if reason is not None:
        return ConsumeResult(user=user, allowed=False, reason=reason)

    return ConsumeResult(
        user=replace(
            user,
            analysis_used=user.analysis_used + count,
            analysis_used_today=user.analysis_used_today + count,
        ),
        allowed=True,
        reason=None,
    )


def activate(user: User, plan: str, settings: Settings, *, now: datetime | None = None) -> User:
    """Upgrade ``user`` to ``plan`` for one billing period, resetting usage."""
    now = now or datetime.now(UTC)
    if plan not in PAID_PLANS:
        raise ValueError(f"Not a purchasable plan: {plan!r}")
    return replace(
        user,
        plan=plan,
        plan_expires_at=now + timedelta(days=settings.plan_billing_period_days),
        analysis_used=0,
        analysis_used_today=0,
        analysis_period_start=now,
        analysis_day_start=_utc_midnight(now),
    )


def status(user: User, settings: Settings, *, now: datetime | None = None) -> PlanStatus:
    """Describe the user's plan and what is left of both quotas.

    ``user`` must already be enforced (see :func:`enforce`); this never mutates.
    """
    now = now or datetime.now(UTC)
    limit = plan_limit(user.plan, settings)
    daily_limit = plan_daily_limit(user.plan, settings)
    active = user.plan == "free" or (
        user.plan_expires_at is not None and user.plan_expires_at > now
    )
    return PlanStatus(
        plan=user.plan,
        limit=limit,
        used=user.analysis_used,
        remaining=-1 if limit == -1 else max(0, limit - user.analysis_used),
        daily_limit=daily_limit,
        used_today=user.analysis_used_today,
        remaining_today=(
            -1 if daily_limit == -1 else max(0, daily_limit - user.analysis_used_today)
        ),
        expires_at=user.plan_expires_at,
        active=active,
        price_usd=plan_price(user.plan, settings),
    )


def _utc_midnight(moment: datetime) -> datetime:
    """Return the UTC midnight that ``moment`` belongs to."""
    if not moment.tzinfo:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


def _advance_period(start: datetime, settings: Settings, now: datetime) -> datetime:
    """Advance ``start`` by whole periods so ``now`` falls inside the period."""
    if not start.tzinfo:
        start = start.replace(tzinfo=UTC)
    period_seconds = settings.plan_billing_period_days * 86_400
    if period_seconds <= 0:
        return now
    elapsed = (now - start).total_seconds() / period_seconds
    if elapsed < 0:
        return start
    steps = int(elapsed)
    return start + timedelta(seconds=steps * period_seconds) if steps else start
