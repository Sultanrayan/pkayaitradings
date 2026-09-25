"""User plan limits, usage accounting and billing-period logic.

Plans (no Enterprise):

* **Free** — 20 analyses per billing period (USD 0)
* **Pro** — 150 analyses per billing period (USD 15)
* **Ultra** — unlimited analyses (USD 65)

A paid plan is active until ``plan_expires_at``; once that moment passes the
user is automatically downgraded to Free. Usage resets at each period boundary
(``plan_billing_period_days``) for every user. Functions are pure — they never
touch persistence — so the API layer decides when to save.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta

from orchestrator.auth import User
from shared.config import Settings

VALID_PLANS = ("free", "pro", "ultra")


@dataclass(frozen=True)
class PlanStatus:
    """The user's plan and remaining usage for the current period."""

    plan: str
    limit: int
    used: int
    remaining: int
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
        "pro": settings.plan_pro_monthly_limit,
        "ultra": settings.plan_ultra_monthly_limit,
    }[plan]


def plan_price(plan: str, settings: Settings) -> float | None:
    """Return the USD price for a purchasable plan, else ``None``."""
    return {"pro": settings.plan_pro_price_usd, "ultra": settings.plan_ultra_price_usd}.get(plan)


def enforce(user: User, settings: Settings, *, now: datetime | None = None) -> User:
    """Downgrade expired plans and roll the usage period forward.

    Returns a new :class:`User` with the enforced state applied; the caller
    persists it when it differs from ``user``.
    """
    now = now or datetime.now(UTC)

    if user.plan in ("pro", "ultra"):
        if user.plan_expires_at is not None and user.plan_expires_at <= now:
            user = replace(
                user,
                plan="free",
                plan_expires_at=None,
                analysis_used=0,
                analysis_period_start=now,
            )

    period_start = _advance_period(user.analysis_period_start, settings, now)
    if period_start != user.analysis_period_start:
        user = replace(user, analysis_period_start=period_start, analysis_used=0)
    return user


def consume(user: User, settings: Settings, *, now: datetime | None = None) -> ConsumeResult:
    """Enforce the plan, then reserve one analysis if the quota allows it."""
    return consume_many(user, settings, count=1, now=now)


def consume_many(
    user: User, settings: Settings, *, count: int, now: datetime | None = None
) -> ConsumeResult:
    """Enforce the plan, then reserve ``count`` analyses if the quota allows."""
    if count < 0:
        raise ValueError("count must be >= 0")
    now = now or datetime.now(UTC)
    user = enforce(user, settings, now=now)
    limit = plan_limit(user.plan, settings)
    if limit != -1 and user.analysis_used + count > limit:
        return ConsumeResult(
            user=user,
            allowed=False,
            reason=f"Monthly analysis limit ({limit}) reached",
        )
    return ConsumeResult(
        user=replace(user, analysis_used=user.analysis_used + count), allowed=True, reason=None
    )


def activate(user: User, plan: str, settings: Settings, *, now: datetime | None = None) -> User:
    """Upgrade ``user`` to ``plan`` for one billing period, resetting usage."""
    now = now or datetime.now(UTC)
    if plan not in ("pro", "ultra"):
        raise ValueError(f"Not a purchasable plan: {plan!r}")
    return replace(
        user,
        plan=plan,
        plan_expires_at=now + timedelta(days=settings.plan_billing_period_days),
        analysis_used=0,
        analysis_period_start=now,
    )


def activate_trial(
    user: User, settings: Settings, *, now: datetime | None = None
) -> tuple[User, bool]:
    """Grant a free Pro trial of ``plan_trial_days``, unless already entitled.

    A user who already holds an active paid/trial plan is left unchanged so the
    trial cannot be re-triggered repeatedly. Returns the (possibly updated)
    user and whether the trial was actually granted.
    """
    now = now or datetime.now(UTC)
    entitled = user.plan in ("pro", "ultra") and user.plan_expires_at is not None and (
        user.plan_expires_at > now
    )
    if entitled:
        return user, False
    upgraded = replace(
        user,
        plan="pro",
        plan_expires_at=now + timedelta(days=settings.plan_trial_days),
        analysis_used=0,
        analysis_period_start=now,
    )
    return upgraded, True


def status(user: User, settings: Settings, *, now: datetime | None = None) -> PlanStatus:
    """Describe the user's plan and remaining quota.

    ``user`` must already be enforced (see :func:`enforce`); this never mutates.
    """
    now = now or datetime.now(UTC)
    limit = plan_limit(user.plan, settings)
    remaining = -1 if limit == -1 else max(0, limit - user.analysis_used)
    active = user.plan == "free" or (
        user.plan_expires_at is not None and user.plan_expires_at > now
    )
    return PlanStatus(
        plan=user.plan,
        limit=limit,
        used=user.analysis_used,
        remaining=remaining,
        expires_at=user.plan_expires_at,
        active=active,
        price_usd=plan_price(user.plan, settings),
    )


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