"""Celery application and scheduled analysis tasks.

Run the worker and beat scheduler with::

    celery -A orchestrator.scheduler worker -l info
    celery -A orchestrator.scheduler beat -l info
"""

from __future__ import annotations

import asyncio
from typing import Any

from celery import Celery

from shared.config import get_settings

_settings = get_settings()

celery_app = Celery(
    "pkay_tdai",
    broker=_settings.redis_url,
    backend=_settings.redis_url,
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    beat_schedule={
        "analyze-all-symbols": {
            "task": "orchestrator.scheduler.analyze_all_symbols",
            "schedule": float(_settings.analysis_interval_seconds),
        }
    },
)


@celery_app.task(name="orchestrator.scheduler.analyze_symbol")  # type: ignore[untyped-decorator]
def analyze_symbol(symbol: str) -> dict[str, Any]:
    """Run one analysis cycle for a single symbol."""
    return asyncio.run(_run_symbol(symbol))


@celery_app.task(name="orchestrator.scheduler.analyze_all_symbols")  # type: ignore[untyped-decorator]
def analyze_all_symbols() -> list[dict[str, Any]]:
    """Run analysis cycles for every configured symbol."""
    return asyncio.run(_run_all())


async def _run_symbol(symbol: str) -> dict[str, Any]:
    from orchestrator.pipeline import run_analysis_cycle

    result = await run_analysis_cycle(symbol)
    return _serialise(result)


async def _run_all() -> list[dict[str, Any]]:
    from orchestrator.pipeline import AnalysisPipeline

    pipeline = await AnalysisPipeline.build()
    try:
        results = await pipeline.run_all()
        return [_serialise(result) for result in results]
    finally:
        await pipeline.close()


def _serialise(result: Any) -> dict[str, Any]:
    return {
        "symbol": result.symbol,
        "correlation_id": result.correlation_id,
        "decision": result.decision.model_dump(mode="json"),
        "technical": result.primary.model_dump(mode="json"),
        "news": result.news.model_dump(mode="json"),
        "risk": result.risk.model_dump(mode="json"),
    }
