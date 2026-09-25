"""Broker abstractions and a deterministic paper-trading broker."""

from __future__ import annotations

import abc
import asyncio
from typing import ClassVar

from shared.logging import get_logger
from shared.schemas.messages import Fill, Order, OrderStatus, Position

_logger = get_logger(__name__)


class Broker(abc.ABC):
    """Abstract broker interface used by the execution layer."""

    @abc.abstractmethod
    async def submit(self, order: Order) -> Fill:
        """Submit an order and return its fill."""

    @abc.abstractmethod
    async def cancel(self, order_id: str) -> bool:
        """Cancel a pending order; return ``True`` if it was cancelled."""

    @abc.abstractmethod
    async def positions(self) -> list[Position]:
        """Return the currently open positions."""

    @abc.abstractmethod
    async def equity(self) -> float:
        """Return current account equity."""

    @abc.abstractmethod
    async def mark_price(self, symbol: str) -> float | None:
        """Return the latest mark price for ``symbol`` if known."""


class PaperBroker(Broker):
    """In-memory broker for paper trading and tests.

    Market orders fill at the order's ``price`` (or the last mark price) with a
    configurable commission. Positions are netted per symbol and mark-to-market
    equity is computed from the supplied marks.

    Args:
        initial_balance: Starting cash balance.
        commission_bps: Commission in basis points of notional.
    """

    def __init__(self, initial_balance: float = 100_000.0, *, commission_bps: float = 1.0) -> None:
        if initial_balance <= 0:
            raise ValueError("initial_balance must be positive")
        self._initial_balance = initial_balance
        self._balance = initial_balance
        self._commission_bps = commission_bps
        self._positions: dict[str, Position] = {}
        self._marks: dict[str, float] = {}
        self._orders: dict[str, Order] = {}
        self._lock = asyncio.Lock()
        self._fills: list[Fill] = []

    @property
    def balance(self) -> float:
        """Cash balance excluding unrealised PnL."""
        return self._balance

    @property
    def fills(self) -> tuple[Fill, ...]:
        """All fills produced so far."""
        return tuple(self._fills)

    def set_price(self, symbol: str, price: float) -> None:
        """Update the mark price used for fills and equity."""
        self._marks[symbol.upper()] = price

    async def mark_price(self, symbol: str) -> float | None:
        return self._marks.get(symbol.upper())

    async def submit(self, order: Order) -> Fill:
        """Fill ``order`` immediately against the current mark."""
        async with self._lock:
            price = order.price or self._marks.get(order.symbol.upper())
            if price is None or price <= 0:
                rejected = Fill(
                    order_id=order.id,
                    symbol=order.symbol,
                    side=order.side,
                    quantity=order.quantity,
                    price=0.0,
                    status=OrderStatus.REJECTED,
                )
                _logger.warning("paper.order_rejected", symbol=order.symbol, reason="no price")
                return rejected

            commission = order.quantity * price * self._commission_bps / 10_000.0
            self._balance -= commission
            self._apply_to_position(order, price)
            self._marks[order.symbol.upper()] = price
            self._orders[order.id] = order

            fill = Fill(
                order_id=order.id,
                symbol=order.symbol,
                side=order.side,
                quantity=order.quantity,
                price=price,
                commission=round(commission, 6),
            )
            self._fills.append(fill)
            _logger.info(
                "paper.filled",
                symbol=order.symbol,
                side=order.side.value,
                quantity=order.quantity,
                price=price,
            )
            return fill

    def _apply_to_position(self, order: Order, price: float) -> None:
        symbol = order.symbol.upper()
        existing = self._positions.get(symbol)
        if existing is None:
            self._positions[symbol] = Position(
                symbol=symbol,
                side=order.side,
                quantity=order.quantity,
                entry_price=price,
                stop_loss=order.stop_loss,
                take_profit=order.take_profit,
            )
            return

        if existing.side is order.side:
            total_quantity = existing.quantity + order.quantity
            weighted = (
                existing.entry_price * existing.quantity + price * order.quantity
            ) / total_quantity
            self._positions[symbol] = existing.model_copy(
                update={"quantity": total_quantity, "entry_price": weighted}
            )
            return

        closing = min(existing.quantity, order.quantity)
        pnl = existing.unrealised_pnl(price) * (closing / existing.quantity)
        self._balance += pnl
        remaining = existing.quantity - order.quantity
        if remaining > 0:
            self._positions[symbol] = existing.model_copy(update={"quantity": remaining})
        elif remaining < 0:
            self._positions[symbol] = Position(
                symbol=symbol,
                side=order.side,
                quantity=abs(remaining),
                entry_price=price,
                stop_loss=order.stop_loss,
                take_profit=order.take_profit,
            )
        else:
            self._positions.pop(symbol, None)

    async def cancel(self, order_id: str) -> bool:
        """Paper orders fill immediately, so cancellation always returns False."""
        return False

    async def positions(self) -> list[Position]:
        return list(self._positions.values())

    async def equity(self) -> float:
        unrealised = 0.0
        for position in self._positions.values():
            mark = self._marks.get(position.symbol)
            if mark is not None:
                unrealised += position.unrealised_pnl(mark)
        return self._balance + unrealised


class UnsupportedBroker(Broker):
    """Placeholder for live brokers that are not configured.

    MT5 and Binance adapters are intentionally left to deployment-specific
    implementations; this class fails loudly instead of pretending to trade.
    """

    name: ClassVar[str] = "unsupported"

    async def submit(self, order: Order) -> Fill:
        raise NotImplementedError("Live broker adapter is not configured")

    async def cancel(self, order_id: str) -> bool:
        raise NotImplementedError("Live broker adapter is not configured")

    async def positions(self) -> list[Position]:
        raise NotImplementedError("Live broker adapter is not configured")

    async def equity(self) -> float:
        raise NotImplementedError("Live broker adapter is not configured")

    async def mark_price(self, symbol: str) -> float | None:
        raise NotImplementedError("Live broker adapter is not configured")
