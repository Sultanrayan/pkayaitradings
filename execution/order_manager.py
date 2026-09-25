"""Order management: validation and lifecycle on top of a :class:`Broker`."""

from __future__ import annotations

from execution.broker_api import Broker
from shared.logging import get_logger
from shared.schemas.enums import Direction
from shared.schemas.messages import Fill, Order, OrderSide, Position

_logger = get_logger(__name__)


class OrderManager:
    """Validates and submits orders through a broker.

    Implements the ``TradeExecutor`` protocol consumed by the Decision Maker.

    Args:
        broker: The broker adapter to trade through.
    """

    def __init__(self, broker: Broker) -> None:
        self.broker = broker

    async def execute(
        self,
        *,
        symbol: str,
        direction: Direction,
        quantity: float,
        price: float | None = None,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> Fill:
        """Validate and submit a market order.

        Args:
            symbol: Instrument ticker.
            direction: ``BULLISH`` (buy) or ``BEARISH`` (sell).
            quantity: Order quantity; must be positive.
            price: Optional limit/reference price.
            stop_loss: Protective stop; must be on the losing side of ``price``.
            take_profit: Target; must be on the winning side of ``price``.

        Raises:
            ValueError: If quantity is non-positive or the stops are on the
                wrong side of the reference price.
        """
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        if direction is Direction.NEUTRAL:
            raise ValueError("Cannot execute a NEUTRAL direction")
        if price is not None:
            _validate_stops(direction, price, stop_loss, take_profit)

        order = Order.from_direction(
            symbol=symbol.upper(),
            direction=direction,
            quantity=quantity,
            price=price,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )
        _logger.info(
            "order_manager.submitting",
            symbol=order.symbol,
            side=order.side.value,
            quantity=order.quantity,
        )
        return await self.broker.submit(order)

    async def close(self, symbol: str, price: float | None = None) -> Fill | None:
        """Close any open position in ``symbol`` at market."""
        positions = await self.broker.positions()
        position = next((p for p in positions if p.symbol == symbol.upper()), None)
        if position is None:
            return None
        return await self.broker.submit(
            Order(
                symbol=position.symbol,
                side=OrderSide.SELL if position.side is OrderSide.BUY else OrderSide.BUY,
                quantity=position.quantity,
                price=price,
            )
        )

    async def positions(self) -> list[Position]:
        """Return the broker's open positions."""
        return await self.broker.positions()

    async def equity(self) -> float:
        """Return current account equity."""
        return await self.broker.equity()

    def set_price(self, symbol: str, price: float) -> None:
        """Update the mark price when the broker supports it."""
        setter = getattr(self.broker, "set_price", None)
        if callable(setter):
            setter(symbol, price)


def _validate_stops(
    direction: Direction,
    price: float,
    stop_loss: float | None,
    take_profit: float | None,
) -> None:
    if stop_loss is not None:
        if direction is Direction.BULLISH and stop_loss >= price:
            raise ValueError("Long stop_loss must be below the entry price")
        if direction is Direction.BEARISH and stop_loss <= price:
            raise ValueError("Short stop_loss must be above the entry price")
    if take_profit is not None:
        if direction is Direction.BULLISH and take_profit <= price:
            raise ValueError("Long take_profit must be above the entry price")
        if direction is Direction.BEARISH and take_profit >= price:
            raise ValueError("Short take_profit must be below the entry price")
