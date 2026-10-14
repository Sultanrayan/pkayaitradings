"""News Monitor agent.

Combines biquote's economic calendar with its aggregated news feed and a
sentiment classifier to flag events that should change position sizing.
"""

from __future__ import annotations

from typing import Any

from agents.base_agent import BaseAgent
from agents.news_monitor.llm_sentiment import (
    SentimentClassifier,
    SentimentResult,
    build_sentiment_classifier,
)
from agents.news_monitor.scrapers.biquote_news import BiquoteNewsSource
from agents.news_monitor.scrapers.economic_calendar import EconomicCalendarSource
from data_pipeline.biquote_client import BiquoteClient
from shared.schemas.enums import AgentName, AlertLevel, Impact
from shared.schemas.market import CalendarEvent, NewsArticle
from shared.schemas.signals import HistoricalReaction, NewsSignal
from shared.utils.time import format_duration, utcnow

_HALT_WINDOW_MINUTES = 60
_REDUCE_WINDOW_MINUTES = 240


class NewsMonitorAgent(BaseAgent):
    """Monitors macro events and news sentiment for a symbol.

    Args:
        client: Optional biquote REST client (owned by the caller if supplied).
        news_source: Optional news source override.
        calendar_source: Optional calendar source override.
        classifier: Optional sentiment classifier override.
        bus: Optional message bus.
        settings: Optional settings override.
    """

    name = AgentName.NEWS_MONITOR

    def __init__(
        self,
        *,
        client: BiquoteClient | None = None,
        news_source: BiquoteNewsSource | None = None,
        calendar_source: EconomicCalendarSource | None = None,
        classifier: SentimentClassifier | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._owns_client = client is None
        self.client = client or BiquoteClient(self.settings)
        self.news = news_source or BiquoteNewsSource(self.client)
        self.calendar = calendar_source or EconomicCalendarSource(self.client)
        self.classifier = classifier or build_sentiment_classifier(self.settings)

    async def stop(self) -> None:
        """Close the REST client when this agent created it."""
        if self._owns_client:
            await self.client.close()

    async def analyze(self, symbol: str, *, horizon_hours: int = 48) -> NewsSignal:
        """Produce a :class:`NewsSignal` for ``symbol`` without publishing."""
        events = await self.calendar.for_symbol(symbol, horizon_hours=horizon_hours)
        articles = await self.news.fetch_symbol_news(symbol, limit=10)

        headline = _select_headline_event(events)
        sentiment_result = await self._classify(articles, headline)

        impact = _max_impact(events)
        alert = _alert_for(headline)
        time_until = _time_until(headline)
        event_name = headline.name if headline is not None else "MARKET_NEWS"

        reasoning = _build_reasoning(symbol, headline, sentiment_result, articles)
        self.log.info(
            "news_monitor.signal",
            symbol=symbol,
            event_name=event_name,
            impact=impact.value,
            sentiment=sentiment_result.sentiment.value,
            alert=alert.value,
        )
        return NewsSignal(
            event=event_name,
            impact=impact,
            affected_symbols=(symbol.upper(),),
            sentiment=sentiment_result.sentiment,
            confidence=sentiment_result.confidence,
            time_until_event=time_until,
            historical_reaction=_historical_reaction(headline, symbol),
            alert=alert,
            reasoning=reasoning,
            # Always a number in [-1, 1]. Derived from the 0..1 sentiment score so
            # it cannot drift from the enum it represents, and 0.0 for NEUTRAL is
            # a legitimate "no news edge" weight rather than a missing value.
            sentiment_score=round(sentiment_result.sentiment.score * 2.0 - 1.0, 4),
            risk_notes=_risk_notes(event_name, impact, time_until, sentiment_result),
        )

    async def run(
        self,
        symbol: str,
        *,
        horizon_hours: int = 48,
        correlation_id: str | None = None,
    ) -> NewsSignal:
        """Analyse news for ``symbol`` and publish the resulting signal."""
        signal = await self._guarded(NewsSignal, self.analyze, symbol, horizon_hours=horizon_hours)
        await self.publish(signal, kind="news_signal", correlation_id=correlation_id)
        return signal

    async def _classify(
        self, articles: list[NewsArticle], headline: CalendarEvent | None
    ) -> SentimentResult:
        texts = [article.title for article in articles]
        if headline is not None:
            texts.append(f"{headline.name} {headline.country_code}")
        return await self.classifier.classify(texts)


def _select_headline_event(events: list[CalendarEvent]) -> CalendarEvent | None:
    """Pick the most relevant event: nearest upcoming, else latest released."""
    if not events:
        return None
    now = utcnow()
    upcoming = sorted(
        (event for event in events if event.time >= now), key=lambda event: event.time
    )
    if upcoming:
        return upcoming[0]
    released = sorted(events, key=lambda event: event.time, reverse=True)
    return released[0]


def _max_impact(events: list[CalendarEvent]) -> Impact:
    if not events:
        return Impact.LOW
    order = {Impact.LOW: 0, Impact.MEDIUM: 1, Impact.HIGH: 2}
    return max((event.importance for event in events), key=lambda impact: order[impact])


def _alert_for(headline: CalendarEvent | None) -> AlertLevel:
    if headline is None or headline.importance is not Impact.HIGH:
        return AlertLevel.NONE
    minutes = (headline.time - utcnow()).total_seconds() / 60.0
    if 0 <= minutes <= _HALT_WINDOW_MINUTES:
        return AlertLevel.HALT_TRADING
    if 0 <= minutes <= _REDUCE_WINDOW_MINUTES:
        return AlertLevel.REDUCE_POSITION_SIZE
    return AlertLevel.MONITOR


def _time_until(headline: CalendarEvent | None) -> str | None:
    if headline is None:
        return None
    delta = headline.time - utcnow()
    if delta.total_seconds() < 0:
        return f"released {format_duration(-delta)} ago"
    return format_duration(delta)


def _risk_notes(
    event_name: str,
    impact: Any,
    time_until: str | None,
    sentiment_result: Any,
) -> str:
    """News-side warnings: the event, its timing, and how contrarian the read is.

    Only genuine conditions are listed. A section padded with "none" reads as an
    oversight rather than a clean result, so an empty event list returns a
    positive statement instead.
    """
    notes: list[str] = []
    if event_name and event_name.lower() not in {"none", "no event", "n/a"}:
        notes.append(f"Event: {event_name}")
    if time_until:
        notes.append(f"in {time_until}")
    impact_value = getattr(impact, "value", str(impact)).lower()
    if impact_value == "high":
        notes.append("high-impact event — expect slippage and widened spreads")
    elif impact_value == "medium":
        notes.append("moderate-impact event — position size should already reflect it")
    score = sentiment_result.sentiment.score
    if score >= 0.75:
        notes.append("headlines are one-sided — crowded positioning unwinds violently")
    elif score <= 0.25:
        notes.append("headlines are one-sided bearish — a bounce is plausible")
    if not notes:
        return "No scheduled event and no directional headline skew."
    return "; ".join(notes) + "."


def _historical_reaction(
    headline: CalendarEvent | None, symbol: str
) -> tuple[HistoricalReaction, ...]:
    """Placeholder for measured event reactions.

    biquote does not expose a price-reaction series per calendar event, so we do
    not fabricate one. A future revision can compute this from stored OHLC.
    """
    return ()


def _build_reasoning(
    symbol: str,
    headline: CalendarEvent | None,
    sentiment: SentimentResult,
    articles: list[NewsArticle],
) -> str:
    parts: list[str] = []
    if headline is not None:
        parts.append(
            f"{headline.importance.value.upper()} {headline.country_code} event "
            f"'{headline.name}' at {headline.time.isoformat()}"
        )
        if headline.actual is not None and headline.forecast is not None:
            parts.append(f"actual {headline.actual} vs forecast {headline.forecast}")
    else:
        parts.append("No high-impact events in the horizon")
    parts.append(f"news sentiment {sentiment.sentiment.value} ({sentiment.rationale})")
    parts.append(f"{len(articles)} articles reviewed for {symbol.upper()}")
    return "; ".join(parts)
