"""Tests for the paper broker and order manager."""

from __future__ import annotations

import pytest

from execution.broker_api import PaperBroker
from execution.order_manager import OrderManager
from shared.schemas.enums import Direction
from shared.schemas.messages import Order, OrderSide, OrderStatus


async def test_paper_broker_fills_market_order() -> None:
    broker = PaperBroker(initial_balance=10_000, commission_bps=10)
    fill = await broker.submit(
        Order(symbol="XAUUSD", side=OrderSide.BUY, quantity=1.0, price=2000.0)
    )
    assert fill.status is OrderStatus.FILLED
    assert fill.price == 2000.0
    assert fill.commission == pytest.approx(2.0)
    assert broker.balance == pytest.approx(9_998.0)


async def test_paper_broker_rejects_without_price() -> None:
    broker = PaperBroker()
    fill = await broker.submit(Order(symbol="XAUUSD", side=OrderSide.BUY, quantity=1.0))
    assert fill.status is OrderStatus.REJECTED


async def test_paper_broker_nets_positions_and_realises_pnl() -> None:
    broker = PaperBroker(initial_balance=10_000, commission_bps=0)
    await broker.submit(Order(symbol="XAUUSD", side=OrderSide.BUY, quantity=1.0, price=2000.0))
    await broker.submit(Order(symbol="XAUUSD", side=OrderSide.BUY, quantity=1.0, price=2010.0))

    positions = await broker.positions()
    assert len(positions) == 1
    assert positions[0].quantity == 2.0
    assert positions[0].entry_price == pytest.approx(2005.0)

    await broker.submit(Order(symbol="XAUUSD", side=OrderSide.SELL, quantity=1.0, price=2020.0))
    positions = await broker.positions()
    assert positions[0].quantity == 1.0
    assert broker.balance == pytest.approx(10_015.0)


async def test_paper_broker_equity_includes_unrealised() -> None:
    broker = PaperBroker(initial_balance=10_000, commission_bps=0)
    broker.set_price("XAUUSD", 2000.0)
    await broker.submit(Order(symbol="XAUUSD", side=OrderSide.BUY, quantity=2.0, price=2000.0))
    broker.set_price("XAUUSD", 2050.0)
    assert await broker.equity() == pytest.approx(10_100.0)


async def test_order_manager_executes_bullish() -> None:
    broker = PaperBroker(initial_balance=10_000, commission_bps=0)
    manager = OrderManager(broker)
    fill = await manager.execute(
        symbol="XAUUSD",
        direction=Direction.BULLISH,
        quantity=1.0,
        price=2000.0,
        stop_loss=1990.0,
        take_profit=2020.0,
    )
    assert fill.status is OrderStatus.FILLED
    assert fill.side is OrderSide.BUY


@pytest.mark.parametrize(
    ("direction", "stop_loss", "take_profit"),
    [
        (Direction.BULLISH, 2010.0, 2020.0),
        (Direction.BULLISH, 1990.0, 1980.0),
        (Direction.BEARISH, 1990.0, 1980.0),
        (Direction.BEARISH, 2010.0, 2020.0),
    ],
)
async def test_order_manager_rejects_wrong_side_stops(
    direction: Direction, stop_loss: float, take_profit: float
) -> None:
    manager = OrderManager(PaperBroker())
    with pytest.raises(ValueError):
        await manager.execute(
            symbol="XAUUSD",
            direction=direction,
            quantity=1.0,
            price=2000.0,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )


async def test_order_manager_rejects_neutral_and_zero_quantity() -> None:
    manager = OrderManager(PaperBroker())
    with pytest.raises(ValueError, match="NEUTRAL"):
        await manager.execute(symbol="XAUUSD", direction=Direction.NEUTRAL, quantity=1.0)
    with pytest.raises(ValueError, match="positive"):
        await manager.execute(symbol="XAUUSD", direction=Direction.BULLISH, quantity=0.0)


async def test_order_manager_close_position() -> None:
    broker = PaperBroker(initial_balance=10_000, commission_bps=0)
    manager = OrderManager(broker)
    await manager.execute(symbol="XAUUSD", direction=Direction.BULLISH, quantity=1.0, price=2000.0)
    fill = await manager.close("XAUUSD", price=2050.0)
    assert fill is not None
    assert fill.side is OrderSide.SELL
    assert await manager.positions() == []
    assert await manager.equity() == pytest.approx(10_050.0)
