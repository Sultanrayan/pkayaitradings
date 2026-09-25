"""Message-bus envelope and execution (order/fill) schemas."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from shared.schemas.enums import AgentName, Direction


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _uuid() -> str:
    return uuid.uuid4().hex


class AgentMessage(BaseModel):
    """Envelope published on the message bus.

    The ``payload`` is one of the agent signal schemas, kept loosely typed so the
    bus stays decoupled from concrete agent implementations.
    """

    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=_uuid)
    source: AgentName
    kind: str
    payload: dict[str, Any]
    correlation_id: str = Field(default_factory=_uuid)
    created_at: datetime = Field(default_factory=_utcnow)


class OrderSide(StrEnum):
    """Direction of an order."""

    BUY = "BUY"
    SELL = "SELL"


class OrderType(StrEnum):
    """Supported order types."""

    MARKET = "MARKET"
    LIMIT = "LIMIT"


class OrderStatus(StrEnum):
    """Lifecycle status of an order."""

    PENDING = "PENDING"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class Order(BaseModel):
    """An order submitted to the execution layer."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=_uuid)
    symbol: str
    side: OrderSide
    order_type: OrderType = OrderType.MARKET
    quantity: float = Field(gt=0)
    price: float | None = Field(default=None, gt=0)
    stop_loss: float | None = Field(default=None, gt=0)
    take_profit: float | None = Field(default=None, gt=0)
    status: OrderStatus = OrderStatus.PENDING
    created_at: datetime = Field(default_factory=_utcnow)

    @classmethod
    def from_direction(
        cls,
        *,
        symbol: str,
        direction: Direction,
        quantity: float,
        price: float | None = None,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> Order:
        """Build an order from a directional signal, or raise for ``NEUTRAL``."""
        if direction is Direction.NEUTRAL:
            raise ValueError("Cannot create an order from a NEUTRAL direction")
        side = OrderSide.BUY if direction is Direction.BULLISH else OrderSide.SELL
        return cls(
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=price,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )


class Fill(BaseModel):
    """The result of an executed order."""

    model_config = ConfigDict(frozen=True)

    order_id: str
    symbol: str
    side: OrderSide
    quantity: float
    price: float
    commission: float = 0.0
    status: OrderStatus = OrderStatus.FILLED
    filled_at: datetime = Field(default_factory=_utcnow)


class Position(BaseModel):
    """An open position held by the broker."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    side: OrderSide
    quantity: float
    entry_price: float
    stop_loss: float | None = None
    take_profit: float | None = None

    def unrealised_pnl(self, mark_price: float) -> float:
        """Mark-to-market PnL at ``mark_price``."""
        delta = mark_price - self.entry_price
        if self.side is OrderSide.SELL:
            delta = -delta
        return delta * self.quantity


MessageKind = Literal[
    "technical_signal",
    "news_signal",
    "trade_proposal",
    "risk_assessment",
    "trade_decision",
    "order_fill",
]
