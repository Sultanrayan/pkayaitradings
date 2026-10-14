"""Celery application and scheduled analysis tasks.

Run the worker and beat scheduler with::

    celery -A orchestrator.scheduler worker -l info
    celery -A orchestrator.scheduler beat -l info

Two schedules run here:

* ``analyze-all-symbols`` every ``analysis_interval_seconds`` runs a full
  four-agent cycle per symbol.
* ``compute-signals`` every ``signal_engine_interval_seconds`` runs the
  bar-anchored signal engine over closed candles. Gated on
  ``signal_engine_enabled``, which ships ``False``.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pandas as pd
from celery import Celery

from orchestrator.store import SignalStore
from shared.config import get_settings
from shared.logging import get_logger
from shared.messaging import create_message_bus

_logger = get_logger(__name__)

_settings = get_settings()


def _utc_now() -> pd.Timestamp:
    """Current time as a timezone-aware UTC ``pd.Timestamp``.

    Read once per pass and passed into the engine, so every symbol in a run is
    evaluated against the same instant. The engine takes the clock as a parameter
    rather than reading one itself, which is what keeps a backtest reproducible.
    """
    return pd.Timestamp.now(tz="UTC")

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
        },
        "compute-signals": {
            "task": "orchestrator.scheduler.compute_signals",
            "schedule": float(_settings.signal_engine_interval_seconds),
        },
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


@celery_app.task(name="orchestrator.scheduler.compute_signals")  # type: ignore[untyped-decorator]
def compute_signals() -> dict[str, Any]:
    """Run the bar-anchored signal engine over closed candles.

    Gated on ``signal_engine_enabled``, which ships ``False``. While disabled this
    returns immediately without fetching data, so the beat can schedule it
    unconditionally and the cost is one no-op task per interval.

    Only *closed* bars are evaluated: ``frame_from_series`` drops the in-progress
    bar at the source, and the engine additionally skips any trailing bar it cannot
    prove closed. That double gate is what makes the engine non-repainting on a
    live feed.
    """
    return asyncio.run(_run_signal_engine())


async def _run_signal_engine() -> dict[str, Any]:
    """Fetch, compute, publish and announce signals for every configured symbol."""
    from data_pipeline.biquote_client import BiquoteClient
    from signals.engine import SignalEngine, frame_from_series
    from signals.models import SignalConfig
    from signals.publisher import publish_signal
    from signals.store import EngineSignalStore

    settings = get_settings()
    if not settings.signal_engine_enabled:
        return {
            "enabled": False,
            "symbols": 0,
            "signals": 0,
            "published": 0,
            "errors": [],
        }

    client = BiquoteClient(settings)
    adapter = EngineSignalStore(SignalStore())
    bus = await create_message_bus(settings)
    config = SignalConfig(
        mode=settings.signal_engine_mode,
        min_bars_between_signals=settings.signal_engine_min_bars_between_signals,
        confirm_on_close=True,
    )
    engine = SignalEngine(config)

    produced: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    symbols = list(settings.trading_symbols)
    # Read once, at the start of the pass. Every bar closed before this instant is
    # closed for every symbol in this run, which is what keeps a multi-symbol pass
    # internally consistent.
    now = _utc_now()

    try:
        for symbol in symbols:
            timeframe = settings.analysis_timeframes[0]
            try:
                series = await client.get_ohlc(
                    symbol, interval=timeframe, limit=settings.signal_engine_lookback
                )
                frame = frame_from_series(series)
                signals = engine.compute(frame, symbol, timeframe.value, now=now)
                for signal in signals:
                    adapter.publish(signal)
                    await publish_signal(bus, signal)
                    produced.append(
                        {
                            "symbol": signal.symbol,
                            "timeframe": signal.timeframe,
                            "action": signal.action,
                            "bar_timestamp": signal.timestamp.isoformat(),
                            "price": signal.price,
                            "confidence": signal.confidence,
                        }
                    )
            except Exception:
                # One symbol's failure must not abandon the rest of the pass.
                _logger.exception(
                    "scheduler.signal_engine_symbol_failed", symbol=symbol, timeframe=timeframe
                )
                errors.append({"symbol": symbol, "timeframe": timeframe})
                continue

        _logger.info(
            "scheduler.signal_engine_pass",
            symbols=len(symbols),
            signals=len(produced),
            errors=len(errors),
        )
        return {
            "enabled": True,
            "symbols": len(symbols),
            "signals": len(produced),
            "published": len(produced),
            "errors": errors,
            "results": produced,
        }
    finally:
        await client.close()
        await bus.close()

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
