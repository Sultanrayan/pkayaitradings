"""Initial schema: market data, signals, trades and risk events.

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-18
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_HYPERTABLES_SQL = """
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_available_extensions WHERE name = 'timescaledb') THEN
        CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;
        PERFORM create_hypertable('ticks', 'timestamp', if_not_exists => TRUE);
        PERFORM create_hypertable('ohlcv', 'open_time', if_not_exists => TRUE);
    END IF;
END
$$;
"""


def upgrade() -> None:
    op.create_table(
        "ticks",
        sa.Column("symbol", sa.String(length=32), primary_key=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), primary_key=True),
        sa.Column("bid", sa.Float(), nullable=False),
        sa.Column("ask", sa.Float(), nullable=False),
        sa.Column("mid", sa.Float(), nullable=False),
        sa.Column("spread", sa.Float(), nullable=False, server_default="0"),
        sa.Column("market_state", sa.String(length=16), nullable=False, server_default="unknown"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ticks_symbol_time", "ticks", ["symbol", "timestamp"])

    op.create_table(
        "ohlcv",
        sa.Column("symbol", sa.String(length=32), primary_key=True),
        sa.Column("timeframe", sa.String(length=8), primary_key=True),
        sa.Column("open_time", sa.DateTime(timezone=True), primary_key=True),
        sa.Column("open", sa.Float(), nullable=False),
        sa.Column("high", sa.Float(), nullable=False),
        sa.Column("low", sa.Float(), nullable=False),
        sa.Column("close", sa.Float(), nullable=False),
        sa.Column("volume", sa.Float(), nullable=False, server_default="0"),
        sa.Column("tick_volume", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_open", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("symbol", "timeframe", "open_time", name="uq_ohlcv_bar"),
    )
    op.create_index("ix_ohlcv_symbol_tf_time", "ohlcv", ["symbol", "timeframe", "open_time"])

    op.create_table(
        "agent_signals",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("correlation_id", sa.String(length=32), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("agent", sa.String(length=32), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_agent_signals_correlation_id", "agent_signals", ["correlation_id"])
    op.create_index("ix_agent_signals_symbol", "agent_signals", ["symbol"])
    op.create_index("ix_agent_signals_agent", "agent_signals", ["agent"])
    op.create_index("ix_agent_signals_kind", "agent_signals", ["kind"])
    op.create_index("ix_agent_signals_created_at", "agent_signals", ["created_at"])

    op.create_table(
        "trades",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("correlation_id", sa.String(length=32), nullable=True),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("stop_loss", sa.Float(), nullable=True),
        sa.Column("take_profit", sa.Float(), nullable=True),
        sa.Column("commission", sa.Float(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="FILLED"),
        sa.Column("reasoning", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_trades_correlation_id", "trades", ["correlation_id"])
    op.create_index("ix_trades_symbol", "trades", ["symbol"])
    op.create_index("ix_trades_created_at", "trades", ["created_at"])

    op.create_table(
        "risk_events",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("correlation_id", sa.String(length=32), nullable=True),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("approved", sa.Boolean(), nullable=False),
        sa.Column("var_95", sa.Float(), nullable=True),
        sa.Column("position_size", sa.Float(), nullable=False, server_default="0"),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_risk_events_correlation_id", "risk_events", ["correlation_id"])
    op.create_index("ix_risk_events_symbol", "risk_events", ["symbol"])
    op.create_index("ix_risk_events_approved", "risk_events", ["approved"])
    op.create_index("ix_risk_events_created_at", "risk_events", ["created_at"])

    op.execute(_HYPERTABLES_SQL)


def downgrade() -> None:
    op.drop_table("risk_events")
    op.drop_table("trades")
    op.drop_table("agent_signals")
    op.drop_table("ohlcv")
    op.drop_table("ticks")
