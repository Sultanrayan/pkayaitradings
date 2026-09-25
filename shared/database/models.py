"""ORM models for time-series market data, signals and trades.

The ``ticks`` and ``ohlcv`` tables are designed as TimescaleDB hypertables; the
migration in ``migrations/versions`` converts them after creation.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from shared.database.base import Base


def _uuid() -> str:
    return uuid.uuid4().hex


def _utcnow() -> datetime:
    return datetime.now(UTC)


class TickRecord(Base):
    """A stored quote. Hypertable on ``timestamp``."""

    __tablename__ = "ticks"

    symbol: Mapped[str] = mapped_column(String(32), primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    bid: Mapped[float] = mapped_column(Float)
    ask: Mapped[float] = mapped_column(Float)
    mid: Mapped[float] = mapped_column(Float)
    spread: Mapped[float] = mapped_column(Float, default=0.0)
    market_state: Mapped[str] = mapped_column(String(16), default="unknown")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (Index("ix_ticks_symbol_time", "symbol", "timestamp"),)


class OhlcvRecord(Base):
    """A stored candle. Hypertable on ``open_time``."""

    __tablename__ = "ohlcv"

    symbol: Mapped[str] = mapped_column(String(32), primary_key=True)
    timeframe: Mapped[str] = mapped_column(String(8), primary_key=True)
    open_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[float] = mapped_column(Float, default=0.0)
    tick_volume: Mapped[int] = mapped_column(Integer, default=0)
    is_open: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (
        UniqueConstraint("symbol", "timeframe", "open_time", name="uq_ohlcv_bar"),
        Index("ix_ohlcv_symbol_tf_time", "symbol", "timeframe", "open_time"),
    )


class AgentSignalRecord(Base):
    """A published agent signal, stored for audit and replay."""

    __tablename__ = "agent_signals"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    correlation_id: Mapped[str] = mapped_column(String(32), index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    agent: Mapped[str] = mapped_column(String(32), index=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True
    )


class TradeRecord(Base):
    """An executed (or rejected) trade."""

    __tablename__ = "trades"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    correlation_id: Mapped[str | None] = mapped_column(String(32), index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    side: Mapped[str] = mapped_column(String(8))
    quantity: Mapped[float] = mapped_column(Float)
    price: Mapped[float] = mapped_column(Float)
    stop_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    take_profit: Mapped[float | None] = mapped_column(Float, nullable=True)
    commission: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(16), default="FILLED")
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True
    )


class RiskEventRecord(Base):
    """A risk assessment decision, including vetoes."""

    __tablename__ = "risk_events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    correlation_id: Mapped[str | None] = mapped_column(String(32), index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    approved: Mapped[bool] = mapped_column(index=True)
    var_95: Mapped[float | None] = mapped_column(Float, nullable=True)
    position_size: Mapped[float] = mapped_column(Float, default=0.0)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True
    )
