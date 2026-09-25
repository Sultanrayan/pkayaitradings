"""Async repository helpers for persisting market data and agent output."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database.models import (
    AgentSignalRecord,
    OhlcvRecord,
    RiskEventRecord,
    TickRecord,
    TradeRecord,
)
from shared.schemas.enums import Timeframe
from shared.schemas.market import OhlcSeries, Tick
from shared.schemas.messages import AgentMessage, Fill
from shared.schemas.signals import RiskAssessment, TradeDecision


async def store_ticks(session: AsyncSession, ticks: Sequence[Tick]) -> int:
    """Upsert ticks, returning the number of rows written."""
    if not ticks:
        return 0
    rows = [
        {
            "symbol": tick.symbol,
            "timestamp": tick.timestamp,
            "bid": tick.bid,
            "ask": tick.ask,
            "mid": tick.mid,
            "spread": tick.spread,
            "market_state": tick.market_state.value,
        }
        for tick in ticks
    ]
    statement = insert(TickRecord).values(rows)
    statement = statement.on_conflict_do_update(
        index_elements=[TickRecord.symbol, TickRecord.timestamp],
        set_={
            "bid": statement.excluded.bid,
            "ask": statement.excluded.ask,
            "mid": statement.excluded.mid,
        },
    )
    result = await session.execute(statement)
    return int(getattr(result, "rowcount", 0) or 0)


async def store_tick(session: AsyncSession, tick: Tick) -> int:
    """Upsert a single tick, returning the number of rows written."""
    return await store_ticks(session, [tick])


async def store_ohlc(session: AsyncSession, series: OhlcSeries, timeframe: Timeframe) -> int:
    """Upsert an OHLC series for ``timeframe``."""
    if not series.bars:
        return 0
    rows = [
        {
            "symbol": series.symbol,
            "timeframe": timeframe.value,
            "open_time": bar.open_time,
            "open": bar.open,
            "high": bar.high,
            "low": bar.low,
            "close": bar.close,
            "volume": bar.volume,
            "tick_volume": bar.tick_volume,
            "is_open": bar.is_open,
        }
        for bar in series.bars
    ]
    statement = insert(OhlcvRecord).values(rows)
    statement = statement.on_conflict_do_update(
        constraint="uq_ohlcv_bar",
        set_={
            "open": statement.excluded.open,
            "high": statement.excluded.high,
            "low": statement.excluded.low,
            "close": statement.excluded.close,
            "tick_volume": statement.excluded.tick_volume,
            "is_open": statement.excluded.is_open,
        },
    )
    result = await session.execute(statement)
    return int(getattr(result, "rowcount", 0) or 0)


async def fetch_recent_ohlc(
    session: AsyncSession, symbol: str, timeframe: Timeframe, *, limit: int = 300
) -> list[OhlcvRecord]:
    """Return the most recent candles for a symbol/timeframe, oldest-first."""
    statement = (
        select(OhlcvRecord)
        .where(
            OhlcvRecord.symbol == symbol.upper(),
            OhlcvRecord.timeframe == timeframe.value,
        )
        .order_by(OhlcvRecord.open_time.desc())
        .limit(limit)
    )
    rows = (await session.execute(statement)).scalars().all()
    return list(reversed(rows))


async def store_agent_message(session: AsyncSession, message: AgentMessage) -> None:
    """Persist an agent message envelope."""
    record = AgentSignalRecord(
        correlation_id=message.correlation_id,
        symbol=str(message.payload.get("symbol", "")),
        agent=message.source.value,
        kind=message.kind,
        payload=message.payload,
    )
    session.add(record)


async def store_risk_event(
    session: AsyncSession,
    assessment: RiskAssessment,
    *,
    correlation_id: str | None = None,
) -> None:
    """Persist a risk assessment, including vetoes."""
    session.add(
        RiskEventRecord(
            correlation_id=correlation_id,
            symbol=assessment.symbol,
            approved=assessment.approved,
            var_95=assessment.var_95,
            position_size=assessment.position_size,
            payload=assessment.model_dump(mode="json"),
        )
    )


async def store_trade(
    session: AsyncSession,
    decision: TradeDecision,
    fill: Fill,
    *,
    correlation_id: str | None = None,
) -> None:
    """Persist an executed trade alongside its decision rationale."""
    session.add(
        TradeRecord(
            id=fill.order_id,
            correlation_id=correlation_id,
            symbol=fill.symbol,
            side=fill.side.value,
            quantity=fill.quantity,
            price=fill.price,
            stop_loss=decision.stop_loss,
            take_profit=decision.take_profit,
            commission=fill.commission,
            status=fill.status.value,
            reasoning=decision.reasoning,
        )
    )
