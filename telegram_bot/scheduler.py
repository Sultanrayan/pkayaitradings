"""Scheduled jobs.

Cron triggers per the specification:

===================  ==========================
Job                  Trigger
===================  ==========================
1mn scan             every minute
5mn scan             ``*/5``
15mn scan            ``*/15``
1h scan              at minute 0
order flow check     every 30 seconds
daily summary        08:00 UTC
weekly summary       Sunday 08:00 UTC
===================  ==========================

All jobs run in UTC. The scheduler is configured with ``timezone="UTC"`` so a host
in another zone cannot shift a scan by an hour — which would mean evaluating a
bar before it closed and is precisely the repaint the engine is built to avoid.

Quiet hours suppress *delivery*, never computation. The scanner already handles
that, so a scan running inside a quiet hour still records signals and the
performance history stays complete.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from shared.logging import get_logger
from telegram_bot.defaults import BotConfig
from telegram_bot.scanner import Scanner, ScanResult

_logger = get_logger(__name__)

__all__ = ["JOBS", "JobDefinition", "build_scheduler", "cron_for_timeframe"]

#: Cron expression per internal timeframe. `1m` fires every minute, which is
#: cheap because the scanner skips a bar it has already processed.
CRON_BY_TIMEFRAME: dict[str, str] = {
    "1m": "* * * * *",
    "5m": "*/5 * * * *",
    "15m": "*/15 * * * *",
    "1h": "0 * * * *",
}


def cron_for_timeframe(timeframe: str) -> str:
    """Cron expression for a timeframe's scan job.

    Args:
        timeframe: Internal timeframe, e.g. ``5m``.

    Returns:
        A five-field cron expression.

    Raises:
        ValueError: For an unrecognised timeframe.
    """
    try:
        return CRON_BY_TIMEFRAME[timeframe]
    except KeyError as exc:
        raise ValueError(f"no cron job for timeframe: {timeframe!r}") from exc


@dataclass(frozen=True)
class JobDefinition:
    """One scheduled job.

    Attributes:
        name: Job id, also the log event suffix.
        cron: Five-field cron expression, UTC.
        description: What the job does, for logs and ``/status``-style debugging.
    """

    name: str
    cron: str
    description: str


#: Every job the bot schedules.
JOBS: tuple[JobDefinition, ...] = (
    JobDefinition("scan-1m", CRON_BY_TIMEFRAME["1m"], "Signal scan, 1 minute"),
    JobDefinition("scan-5m", CRON_BY_TIMEFRAME["5m"], "Signal scan, 5 minutes"),
    JobDefinition("scan-15m", CRON_BY_TIMEFRAME["15m"], "Signal scan, 15 minutes"),
    JobDefinition("scan-1h", CRON_BY_TIMEFRAME["1h"], "Signal scan, hourly"),
    JobDefinition("order-flow", "*/30 * * * *", "Order-flow refresh, 30 seconds"),
    JobDefinition("daily-summary", "0 8 * * *", "Daily summary, 08:00 UTC"),
    JobDefinition("weekly-summary", "0 8 * * 0", "Weekly summary, Sunday 08:00 UTC"),
)


def build_scheduler(
    *,
    scanner: Scanner,
    config: BotConfig,
    deliver: Callable[[ScanResult], Awaitable[None]],
    summarise: Callable[[bool], Awaitable[None]] | None = None,
    apscheduler: Any = None,
) -> Any:
    """Register every job on an :class:`~apscheduler.schedulers.asyncio.AsyncIOScheduler`.

    Args:
        scanner: Scanner to run.
        config: Bot configuration.
        deliver: Coroutine that sends a scan's results. Injected so this function
            never touches Telegram and stays testable.
        summarise: Coroutine for the daily and weekly summaries, receiving
            ``True`` for weekly. ``None`` skips both jobs.
        apscheduler: The scheduler class. Injectable so a test can pass
            ``BackgroundScheduler`` and inspect the jobs without an event loop.

    Returns:
        The configured scheduler, not yet started.

    Note:
        Each timeframe gets its own job rather than one job filtering by
        timeframe. A single job firing every minute and filtering would wake the
        scheduler 12 times an hour for no work, and the per-timeframe cron is the
        scheduling primitive the spec asks for.
    """
    if apscheduler is None:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler

        apscheduler = AsyncIOScheduler

    scheduler = apscheduler(timezone="UTC")

    async def _run_scan(timeframe: str) -> None:
        result = await scanner.scan(timeframe=timeframe)
        if result.has_deliveries and deliver is not None:
            await deliver(result)

    for timeframe in ("1m", "5m", "15m", "1h"):
        if timeframe not in scanner.db.timeframes_for(scanner.db.symbols()[0]):
            continue
        scheduler.add_job(
            _run_scan,
            "cron",
            id=f"scan-{timeframe}",
            args=(timeframe,),
            **parse_cron(CRON_BY_TIMEFRAME[timeframe]),
            max_instances=1,
            coalesce=True,
            misfire_grace_time=30,
            replace_existing=True,
        )

    async def _order_flow() -> None:
        # Refresh the cache the ``/orderflow`` command reads. No signal
        # computation: this job exists so the command is never stale.
        pairs = scanner.db.all_pairs()
        await scanner.collect_order_flow(pairs)

    scheduler.add_job(
        _order_flow,
        "cron",
        id="order-flow",
        minute="*/30",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )

    if summarise is not None:

        async def _daily() -> None:
            await summarise(False)

        async def _weekly() -> None:
            await summarise(True)

        scheduler.add_job(
            _daily,
            "cron",
            id="daily-summary",
            hour=8,
            minute=0,
            max_instances=1,
            coalesce=True,
            replace_existing=True,
        )
        scheduler.add_job(
            _weekly,
            "cron",
            id="weekly-summary",
            day_of_week="sun",
            hour=8,
            minute=0,
            max_instances=1,
            coalesce=True,
            replace_existing=True,
        )

    _logger.info(
        "scheduler.built",
        jobs=[job.name for job in scheduler.get_jobs()] if scheduler.get_jobs() else [],
    )
    return scheduler


def parse_cron(expression: str) -> dict[str, Any]:
    """Split a five-field cron expression into APScheduler keyword arguments.

    APScheduler wants keyword fields rather than a positional expression, and
    accepts ``minute``/``hour``/``day_of_week`` with the usual cron syntax.

    Args:
        expression: Five space-separated fields: minute hour day month weekday.

    Returns:
        Keyword arguments for ``add_job(trigger="cron", ...)``.

    Raises:
        ValueError: When the expression does not have exactly five fields.
    """
    fields = expression.split()
    if len(fields) != 5:
        raise ValueError(f"cron needs 5 fields, got {len(fields)}: {expression!r}")
    minute, hour, day, month, day_of_week = fields
    return {
        "minute": minute,
        "hour": hour,
        "day": day,
        "month": month,
        "day_of_week": day_of_week,
    }


def summarise_performance(
    scanner: Scanner,
    *,
    days: int,
    now: int,
) -> dict[str, Any]:
    """Compute the aggregate figures a daily or weekly summary reports.

    Split out from the job so the arithmetic is testable without a scheduler.

    Args:
        scanner: Scanner holding the database.
        days: Window length in days.
        now: Current Unix seconds.

    Returns:
        Counts and rates for the window.
    """
    since = now - days * 86_400
    rows = scanner.db.signals_in_range(since, now)
    resolved = [r for r in rows if r.outcome in ("win", "loss")]
    wins = sum(1 for r in resolved if r.outcome == "win")
    scored = [r for r in resolved if r.pnl_pct is not None]
    pnl_values = [float(r.pnl_pct or 0.0) for r in scored]

    rr_values = []
    for row in resolved:
        risk = abs(row.entry - row.sl)
        if risk > 0:
            rr_values.append(abs(row.tp2 - row.entry) / risk)

    return {
        "days": days,
        "signals": len(rows),
        "resolved": len(resolved),
        "wins": wins,
        "losses": len(resolved) - wins,
        "win_rate": (wins / len(resolved) * 100.0) if resolved else 0.0,
        "avg_rr": (sum(rr_values) / len(rr_values)) if rr_values else 0.0,
        "total_pnl_pct": sum(pnl_values),
        "best_pnl_pct": max(pnl_values) if pnl_values else 0.0,
        "worst_pnl_pct": min(pnl_values) if pnl_values else 0.0,
    }
