"""Tests for the end-to-end analysis pipeline."""

from __future__ import annotations

from datetime import timedelta

from agents.decision_maker.agent import DecisionMakerAgent
from agents.news_monitor.agent import NewsMonitorAgent
from agents.news_monitor.llm_sentiment import LexiconSentimentClassifier
from agents.risk_manager.agent import RiskManagerAgent
from agents.technical_analyst.agent import TechnicalAnalystAgent
from execution.broker_api import PaperBroker
from execution.order_manager import OrderManager
from orchestrator.pipeline import AnalysisPipeline
from shared.config import Settings
from shared.messaging import InMemoryMessageBus
from shared.schemas.enums import Decision, Direction, MarketState, Timeframe
from shared.schemas.market import OhlcSeries, Tick
from shared.utils.time import utcnow
from tests.test_news_monitor import _StubCalendar, _StubNews
from tests.test_strategy import make_series


class _StubClient:
    """Serves synthetic OHLC for both signal generation and returns context."""

    def __init__(self, series: OhlcSeries) -> None:
        self._series = series
        self.calls: list[Timeframe] = []

    async def get_ohlc(
        self, symbol: str, *, interval: Timeframe = Timeframe.H1, limit: int = 300
    ) -> OhlcSeries:
        self.calls.append(interval)
        return self._series

    async def get_tick(self, symbol: str, *, allow_stale: bool = True) -> Tick:
        price = self._series.latest_close or 1.0
        return Tick(
            symbol=symbol,
            bid=price - 0.1,
            ask=price + 0.1,
            mid=price,
            timestamp=utcnow(),
            marketState=MarketState.OPEN.value,
        )

    async def close(self) -> None:
        return None


def _build_pipeline(settings: Settings, series: OhlcSeries) -> AnalysisPipeline:
    bus = InMemoryMessageBus()
    client = _StubClient(series)
    broker = PaperBroker(settings.paper_initial_balance)
    return AnalysisPipeline(
        technical=TechnicalAnalystAgent(client=client, bus=bus, settings=settings),
        news=NewsMonitorAgent(
            news_source=_StubNews([]),
            calendar_source=_StubCalendar([]),
            classifier=LexiconSentimentClassifier(),
            bus=bus,
            settings=settings,
        ),
        risk=RiskManagerAgent(bus=bus, settings=settings),
        decision=DecisionMakerAgent(executor=OrderManager(broker), bus=bus, settings=settings),
        client=client,  # type: ignore[arg-type]
        settings=settings,
    )


async def test_cycle_executes_approved_uptrend(settings: Settings) -> None:
    pipeline = _build_pipeline(settings, make_series(300, drift=0.6))
    result = await pipeline.run_cycle("XAUUSD", [Timeframe.H1])

    assert result.primary.signal is Direction.BULLISH
    assert result.risk.approved is True
    assert result.decision.decision is Decision.BUY
    assert result.traded is True
    assert result.decision.order_id is not None


async def test_cycle_skips_without_direction(settings: Settings) -> None:
    flat = make_series(300, drift=0.0, seed=99)
    pipeline = _build_pipeline(settings, flat)
    result = await pipeline.run_cycle("XAUUSD", [Timeframe.H1])

    assert result.decision.decision in {Decision.WAIT, Decision.SKIP}
    assert result.traded is False


async def test_run_all_handles_multiple_symbols(settings: Settings) -> None:
    pipeline = _build_pipeline(settings, make_series(300, drift=0.4))
    results = await pipeline.run_all(["XAUUSD", "BTCUSD"])
    assert [result.symbol for result in results] == ["XAUUSD", "BTCUSD"]


async def test_pipeline_context_uses_daily_returns(settings: Settings) -> None:
    client = _StubClient(make_series(300, drift=0.5))
    pipeline = _build_pipeline(settings, client._series)
    pipeline.client = client  # type: ignore[assignment]
    await pipeline.run_cycle("XAUUSD", [Timeframe.H1])
    assert Timeframe.D1 in client.calls


def test_stub_calendar_returns_events_relative_to_now() -> None:
    from shared.schemas.enums import Impact
    from tests.test_news_monitor import make_event

    event = make_event(minutes_from_now=10, importance=Impact.HIGH)
    assert event.time > utcnow() - timedelta(minutes=1)
