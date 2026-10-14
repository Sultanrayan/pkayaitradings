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
    """Directional view on a market.

    .. deprecated:: NEUTRAL
        ``NEUTRAL`` is retained for compatibility and is still load-bearing
        outside the four agents — ``orchestrator/pipeline.py``,
        ``orchestrator/store.py``, ``shared/schemas/messages.py`` and
        ``execution/order_manager.py`` all branch on it. The four agents no
        longer emit it: they always publish BULLISH or BEARISH and express
        low conviction through ``TechnicalSignal.confidence`` and
        ``Strength.WEAK`` instead. Do not delete this member.
    """

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
    """Macro/news sentiment classification.

    ``NEUTRAL`` is a **weight**, not a gate: it scores ``0.5``, meaning "no news
    edge either way". It is not a non-actionable outcome and must not be read as
    one — the news monitor always returns a sentiment, and sentiment only ever
    adjusts the combined confidence rather than blocking a signal.
    """

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
    """Final decision produced by the decision maker.

    .. deprecated:: WAIT, SKIP
        The decision maker now always returns ``BUY`` or ``SELL``. ``WAIT`` and
        ``SKIP`` are retained because the Risk Manager's **drawdown veto** still
        maps to ``SKIP`` — that is a loss-limiting control, not a signal stance —
        and because ``orchestrator`` and the execution layer branch on these
        members. Do not delete them. ``WAIT`` has no remaining producer.
    """

    BUY = "BUY"
    SELL = "SELL"
    WAIT = "WAIT"
    SKIP = "SKIP"


class Strength(StrEnum):
    """Conviction band derived from a signal's confidence.

    Replaces the non-actionable outcomes the agents used to return. A market with
    no edge is now expressed as a directional call at ``WEAK`` with a small
    position size, rather than as a refusal to call.

    Bands are defined once, here, so the agents and the Telegram bot cannot drift
    apart in where they draw the line.
    """

    WEAK = "WEAK"
    MODERATE = "MODERATE"
    STRONG = "STRONG"

    @classmethod
    def from_confidence(cls, confidence: float) -> Strength:
        """Band a ``[0, 1]`` confidence.

        Args:
            confidence: Conviction, where ``0.0`` is a coin flip and ``1.0`` is
                maximal agreement.

        Returns:
            ``WEAK`` below 0.30, ``MODERATE`` up to 0.70, ``STRONG`` above.
        """
        value = max(0.0, min(1.0, float(confidence)))
        if value < 0.30:
            return cls.WEAK
        if value <= 0.70:
            return cls.MODERATE
        return cls.STRONG

    @property
    def position_size(self) -> float:
        """Recommended position size for this band.

        The size is what makes a low-conviction call survivable: a ``WEAK``
        signal is still taken, at a quarter of normal risk.
        """
        return {
            Strength.WEAK: 0.25,
            Strength.MODERATE: 0.60,
            Strength.STRONG: 1.00,
        }[self]


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
