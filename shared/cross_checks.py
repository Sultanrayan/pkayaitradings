"""Cross-agent consistency checks (backend-v2, Problem 3).

Agents can disagree — e.g. Technical = BULLISH while News = BEARISH. Before a
decision is produced this layer inspects the technical and news signals, records
warnings and applies a confidence penalty so the Decision Maker *downgrades*
conflicting inputs instead of averaging them.

Also provides multi-timeframe confirmation (Problem 6): when several timeframes
are analysed, the structural roles are H4 = bias, H1 = setup, M15 = entry and
M5 = trigger, and a strong signal requires at least 3/4 of the directional
timeframes to align with the primary direction.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from shared.schemas.enums import AlertLevel, Direction, Sentiment, Timeframe
from shared.schemas.signals import NewsSignal, TechnicalSignal

_MAX_CONFLICT_PENALTY = 0.20
_HALF_PENALTY = _MAX_CONFLICT_PENALTY / 2


@dataclass(frozen=True)
class CrossCheckResult:
    """Outcome of inspecting the technical and news signals together."""

    consistent: bool
    warnings: tuple[str, ...]
    confidence_penalty: float


@dataclass(frozen=True)
class TimeframeAlignment:
    """How many directional timeframes agree with the primary direction."""

    aligned: int
    total: int

    @property
    def strong(self) -> bool:
        """At least 3/4 of the analysed timeframes must align.

        A single-timeframe analysis is never penalised (there is nothing to
        contradict it).
        """
        if self.total < 2:
            return True
        return self.aligned >= math.ceil(0.75 * self.total)


def sentiment_direction(sentiment: Sentiment) -> Direction:
    """Map a news sentiment to a coarse directional view."""
    if sentiment in {Sentiment.VERY_BULLISH, Sentiment.BULLISH}:
        return Direction.BULLISH
    if sentiment in {Sentiment.VERY_BEARISH, Sentiment.BEARISH}:
        return Direction.BEARISH
    return Direction.NEUTRAL


def check_consistency(technical: TechnicalSignal, news: NewsSignal) -> CrossCheckResult:
    """Detect conflicts between the technical and news signals.

    Returns a :class:`CrossCheckResult` with human-readable warnings and a
    confidence penalty (``0.0`` when consistent) the Decision Maker subtracts
    from the technical confidence before scoring.
    """
    warnings: list[str] = []
    penalty = 0.0

    news_direction = sentiment_direction(news.sentiment)
    if (
        technical.signal is not Direction.NEUTRAL
        and news_direction is not Direction.NEUTRAL
        and technical.signal is not news_direction
    ):
        penalty = _MAX_CONFLICT_PENALTY
        warnings.append(
            f"Technical {technical.signal.value} conflicts with news sentiment "
            f"{news.sentiment.value}"
        )

    if news.alert is AlertLevel.HALT_TRADING:
        penalty = max(penalty, _MAX_CONFLICT_PENALTY)
        warnings.append("News monitor issued a trading halt alert")
    elif news.alert is AlertLevel.REDUCE_POSITION_SIZE:
        penalty = max(penalty, _HALF_PENALTY)
        warnings.append("News monitor advises reducing position size")

    return CrossCheckResult(
        consistent=penalty < 1e-9,
        warnings=tuple(warnings),
        confidence_penalty=penalty,
    )


def confirm_timeframes(
    signals: dict[Timeframe, TechnicalSignal], primary: TechnicalSignal
) -> TimeframeAlignment:
    """Count how many directional timeframes agree with the primary signal.

    Neutral signals do not vote, so a single aligned directional timeframe (or
    no second opinion at all) is treated as strong.
    """
    directional = [signal for signal in signals.values() if signal.signal is not Direction.NEUTRAL]
    aligned = sum(1 for signal in directional if signal.signal is primary.signal)
    return TimeframeAlignment(aligned=aligned, total=len(directional))
