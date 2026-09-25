"""Enumerations shared across agents and schemas."""

from __future__ import annotations

from enum import StrEnum


class AgentName(StrEnum):
    """Canonical agent identifiers used on the message bus."""

    TECHNICAL_ANALYST = "technical_analyst"
    NEWS_MONITOR = "news_monitor"
    RISK_MANAGER = "risk_manager"
    DECISION_MAKER = "decision_maker"
    ORCHESTRATOR = "orchestrator"


class Direction(StrEnum):
    """Directional view on a market."""

    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"

    @property
    def score(self) -> float:
        """Map the direction to a ``[0, 1]`` conviction score."""
        return {
            Direction.BULLISH: 1.0,
            Direction.NEUTRAL: 0.5,
            Direction.BEARISH: 0.0,
        }[self]


class Sentiment(StrEnum):
    """Macro/news sentiment classification."""

    VERY_BULLISH = "VERY_BULLISH"
    BULLISH = "BULLISH"
    NEUTRAL = "NEUTRAL"
    BEARISH = "BEARISH"
    VERY_BEARISH = "VERY_BEARISH"

    @property
    def score(self) -> float:
        """Map sentiment to a ``[0, 1]`` score (bullish = high)."""
        return {
            Sentiment.VERY_BULLISH: 1.0,
            Sentiment.BULLISH: 0.75,
            Sentiment.NEUTRAL: 0.5,
            Sentiment.BEARISH: 0.25,
            Sentiment.VERY_BEARISH: 0.0,
        }[self]


class Impact(StrEnum):
    """Expected market impact of an event."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class AlertLevel(StrEnum):
    """Actionable alert emitted by the news monitor."""

    NONE = "NONE"
    MONITOR = "MONITOR"
    REDUCE_POSITION_SIZE = "REDUCE_POSITION_SIZE"
    HALT_TRADING = "HALT_TRADING"


class Decision(StrEnum):
    """Final decision produced by the decision maker."""

    BUY = "BUY"
    SELL = "SELL"
    WAIT = "WAIT"
    SKIP = "SKIP"


class MarketState(StrEnum):
    """biquote market session state."""

    OPEN = "open"
    CLOSED = "closed"
    UNKNOWN = "unknown"


class Timeframe(StrEnum):
    """Supported candle intervals, mapped to biquote intervals."""

    M1 = "M1"
    M5 = "M5"
    M15 = "M15"
    M30 = "M30"
    H1 = "H1"
    H4 = "H4"
    D1 = "D1"

    @property
    def biquote_interval(self) -> str:
        """biquote OHLC interval string for this timeframe."""
        return {
            Timeframe.M1: "1m",
            Timeframe.M5: "5m",
            Timeframe.M15: "15m",
            Timeframe.M30: "30m",
            Timeframe.H1: "1h",
            Timeframe.H4: "4h",
            Timeframe.D1: "1d",
        }[self]

    @property
    def seconds(self) -> int:
        """Duration of one bar in seconds."""
        return {
            Timeframe.M1: 60,
            Timeframe.M5: 300,
            Timeframe.M15: 900,
            Timeframe.M30: 1_800,
            Timeframe.H1: 3_600,
            Timeframe.H4: 14_400,
            Timeframe.D1: 86_400,
        }[self]
