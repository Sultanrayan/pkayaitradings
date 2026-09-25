"""Tests for the News Monitor agent, sentiment and calendar helpers."""

from __future__ import annotations

import asyncio
from datetime import timedelta

from agents.news_monitor.agent import NewsMonitorAgent
from agents.news_monitor.llm_sentiment import LexiconSentimentClassifier
from agents.news_monitor.scrapers.economic_calendar import quote_currency
from shared.messaging import InMemoryMessageBus
from shared.schemas.enums import AlertLevel, Impact, Sentiment
from shared.schemas.market import CalendarEvent, NewsArticle
from shared.schemas.messages import AgentMessage
from shared.utils.time import utcnow


def make_event(
    *,
    minutes_from_now: float,
    importance: Impact = Impact.HIGH,
    name: str = "Nonfarm Payrolls",
    currency: str = "USD",
) -> CalendarEvent:
    return CalendarEvent(
        id="mql5:1",
        eventId="mql5:840",
        time=utcnow() + timedelta(minutes=minutes_from_now),
        countryCode="US",
        currency=currency,
        name=name,
        importance=importance,
    )


class _StubNews:
    def __init__(self, articles: list[NewsArticle]) -> None:
        self._articles = articles

    async def fetch_symbol_news(
        self, symbol: str, *, limit: int = 10, **_: object
    ) -> list[NewsArticle]:
        return self._articles

    async def fetch_market_news(self, *, limit: int = 10, **_: object) -> list[NewsArticle]:
        return self._articles


class _StubCalendar:
    def __init__(self, events: list[CalendarEvent]) -> None:
        self._events = events

    async def for_symbol(
        self, symbol: str, *, horizon_hours: int = 48, **_: object
    ) -> list[CalendarEvent]:
        return self._events

    async def upcoming(self, **_: object) -> list[CalendarEvent]:
        return self._events


def test_quote_currency() -> None:
    assert quote_currency("XAUUSD") == "USD"
    assert quote_currency("BTCUSD") == "USD"
    assert quote_currency("EURUSD") == "USD"
    assert quote_currency("USDJPY") == "JPY"


async def test_lexicon_classifies_bullish() -> None:
    result = await LexiconSentimentClassifier().classify(
        ["Gold rallies to record high as Fed turns dovish"]
    )
    assert result.sentiment in {Sentiment.BULLISH, Sentiment.VERY_BULLISH}
    assert result.confidence > 0.4


async def test_lexicon_classifies_bearish() -> None:
    result = await LexiconSentimentClassifier().classify(
        ["Bitcoin plunges as Fed signals hawkish rate hike"]
    )
    assert result.sentiment in {Sentiment.BEARISH, Sentiment.VERY_BEARISH}


async def test_lexicon_neutral_when_no_terms() -> None:
    result = await LexiconSentimentClassifier().classify(["Company names its new CFO"])
    assert result.sentiment is Sentiment.NEUTRAL


async def test_imminent_high_impact_event_halts_trading() -> None:
    agent = NewsMonitorAgent(
        news_source=_StubNews([]),
        calendar_source=_StubCalendar([make_event(minutes_from_now=30)]),
        classifier=LexiconSentimentClassifier(),
    )
    signal = await agent.analyze("XAUUSD")
    assert signal.alert is AlertLevel.HALT_TRADING
    assert signal.impact is Impact.HIGH
    assert signal.time_until_event is not None


async def test_event_within_reduce_window() -> None:
    agent = NewsMonitorAgent(
        news_source=_StubNews([]),
        calendar_source=_StubCalendar([make_event(minutes_from_now=180)]),
        classifier=LexiconSentimentClassifier(),
    )
    signal = await agent.analyze("XAUUSD")
    assert signal.alert is AlertLevel.REDUCE_POSITION_SIZE


async def test_no_events_is_low_impact_none() -> None:
    agent = NewsMonitorAgent(
        news_source=_StubNews([]),
        calendar_source=_StubCalendar([]),
        classifier=LexiconSentimentClassifier(),
    )
    signal = await agent.analyze("BTCUSD")
    assert signal.impact is Impact.LOW
    assert signal.alert is AlertLevel.NONE
    assert signal.event == "MARKET_NEWS"


async def test_run_publishes_news_signal() -> None:
    bus = InMemoryMessageBus()
    agent = NewsMonitorAgent(
        bus=bus,
        news_source=_StubNews([]),
        calendar_source=_StubCalendar([]),
        classifier=LexiconSentimentClassifier(),
    )

    async def first() -> AgentMessage:
        async for message in bus.subscribe("signals.news_monitor"):
            return message
        raise AssertionError("no message")  # pragma: no cover

    task = asyncio.create_task(first())
    await asyncio.sleep(0)
    await agent.run("XAUUSD")
    message = await asyncio.wait_for(task, timeout=2.0)
    assert message.kind == "news_signal"
