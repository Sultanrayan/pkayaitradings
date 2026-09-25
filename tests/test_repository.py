"""Tests for the database repository and session helpers using stub sessions."""

from __future__ import annotations

from typing import Any

from shared.database.base import session_scope
from shared.database.repository import (
    fetch_recent_ohlc,
    store_agent_message,
    store_ohlc,
    store_risk_event,
    store_tick,
    store_ticks,
    store_trade,
)
from shared.schemas.enums import AgentName, MarketState, Timeframe
from shared.schemas.market import OhlcBar, OhlcSeries, Tick
from shared.schemas.messages import AgentMessage, Fill, OrderSide
from shared.schemas.signals import RiskAssessment, TradeDecision
from shared.utils.time import utcnow


class _Result:
    rowcount = 1

    def scalars(self) -> _Result:
        return self

    def all(self) -> list[Any]:
        return []


class _StubSession:
    def __init__(self) -> None:
        self.executed: list[Any] = []
        self.added: list[Any] = []

    async def execute(self, statement: Any) -> _Result:
        self.executed.append(statement)
        return _Result()

    def add(self, obj: Any) -> None:
        self.added.append(obj)


def _tick() -> Tick:
    return Tick(
        symbol="XAUUSD",
        bid=1.0,
        ask=1.2,
        mid=1.1,
        spread=0.2,
        timestamp=utcnow(),
        marketState=MarketState.OPEN.value,
    )


async def test_store_ticks_and_tick() -> None:
    session = _StubSession()
    assert await store_ticks(session, [_tick()]) == 1  # type: ignore[arg-type]
    assert await store_tick(session, _tick()) == 1  # type: ignore[arg-type]


async def test_store_ohlc() -> None:
    series = OhlcSeries(
        symbol="XAUUSD",
        interval="1h",
        bars=(OhlcBar(openTime=utcnow(), open=1, high=2, low=0.5, close=1.5, isOpen=False),),
    )
    session = _StubSession()
    assert await store_ohlc(session, series, Timeframe.H1) == 1  # type: ignore[arg-type]
    assert await store_ohlc(session, OhlcSeries(symbol="X", interval="1h"), Timeframe.H1) == 0  # type: ignore[arg-type]


async def test_fetch_recent_ohlc() -> None:
    session = _StubSession()
    assert await fetch_recent_ohlc(session, "XAUUSD", Timeframe.H1, limit=5) == []  # type: ignore[arg-type]


async def test_store_agent_message() -> None:
    session = _StubSession()
    message = AgentMessage(
        source=AgentName.TECHNICAL_ANALYST, kind="technical_signal", payload={"symbol": "XAUUSD"}
    )
    await store_agent_message(session, message)  # type: ignore[arg-type]
    assert session.added


async def test_store_risk_event() -> None:
    session = _StubSession()
    assessment = RiskAssessment(symbol="XAUUSD", approved=True, var_95=0.01)
    await store_risk_event(session, assessment, correlation_id="c1")  # type: ignore[arg-type]
    assert session.added[0].approved is True


async def test_store_trade() -> None:
    session = _StubSession()
    decision = TradeDecision(
        symbol="XAUUSD",
        decision="BUY",
        final_score=0.8,
        technical_score=0.9,
        news_score=0.6,
        risk_score=1.0,
        risk_approved=True,
        stop_loss=2600.0,
        take_profit=2700.0,
    )
    fill = Fill(order_id="o1", symbol="XAUUSD", side=OrderSide.BUY, quantity=1.0, price=2650.0)
    await store_trade(session, decision, fill, correlation_id="c1")  # type: ignore[arg-type]
    assert session.added[0].id == "o1"


async def test_session_scope_commits() -> None:
    class _Session:
        committed = False
        rolled_back = False
        closed = False

        async def commit(self) -> None:
            self.committed = True

        async def rollback(self) -> None:
            self.rolled_back = True

        async def close(self) -> None:
            self.closed = True

    session = _Session()

    def factory() -> _Session:
        return session

    async with session_scope(factory) as active:  # type: ignore[arg-type]
        assert active is session
    assert session.committed and session.closed


async def test_session_scope_rolls_back_on_error() -> None:
    class _Session:
        rolled_back = False

        async def commit(self) -> None:  # pragma: no cover
            raise AssertionError("should not commit")

        async def rollback(self) -> None:
            self.rolled_back = True

        async def close(self) -> None:
            return None

    session = _Session()

    def factory() -> _Session:
        return session

    try:
        async with session_scope(factory) as _:  # type: ignore[arg-type]
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    assert session.rolled_back


async def test_init_models_calls_create_all() -> None:
    from shared.database.base import init_models

    class _Connection:
        called = False

        async def run_sync(self, fn: Any) -> None:
            self.called = True

    connection = _Connection()

    class _Begin:
        async def __aenter__(self) -> _Connection:
            return connection

        async def __aexit__(self, *args: Any) -> bool:
            return False

    class _Engine:
        def begin(self) -> _Begin:
            return _Begin()

    await init_models(_Engine())  # type: ignore[arg-type]
    assert connection.called
