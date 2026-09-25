"""Tests for cross-agent consistency checks and multi-timeframe alignment."""

from __future__ import annotations

import pytest

from shared.cross_checks import (
    TimeframeAlignment,
    check_consistency,
    confirm_timeframes,
    sentiment_direction,
)
from shared.schemas.enums import AlertLevel, Direction, Sentiment, Timeframe
from shared.schemas.signals import NewsSignal, TechnicalSignal


def make_technical(
    direction: Direction = Direction.BULLISH, confidence: float = 0.8
) -> TechnicalSignal:
    return TechnicalSignal(
        symbol="XAUUSD", timeframe=Timeframe.H1, signal=direction, confidence=confidence
    )


def make_news(
    sentiment: Sentiment = Sentiment.BULLISH,
    confidence: float = 0.8,
    alert: AlertLevel = AlertLevel.NONE,
) -> NewsSignal:
    return NewsSignal(event="FOMC", sentiment=sentiment, confidence=confidence, alert=alert)


def test_sentiment_direction_mapping() -> None:
    assert sentiment_direction(Sentiment.VERY_BULLISH) is Direction.BULLISH
    assert sentiment_direction(Sentiment.BULLISH) is Direction.BULLISH
    assert sentiment_direction(Sentiment.NEUTRAL) is Direction.NEUTRAL
    assert sentiment_direction(Sentiment.BEARISH) is Direction.BEARISH
    assert sentiment_direction(Sentiment.VERY_BEARISH) is Direction.BEARISH


def test_consistent_signals_have_no_penalty() -> None:
    result = check_consistency(make_technical(Direction.BULLISH), make_news(Sentiment.BULLISH))
    assert result.consistent is True
    assert result.confidence_penalty == 0.0
    assert result.warnings == ()


def test_conflicting_signals_apply_penalty() -> None:
    result = check_consistency(make_technical(Direction.BULLISH), make_news(Sentiment.BEARISH))
    assert result.consistent is False
    assert result.confidence_penalty == pytest.approx(0.20)
    assert any("conflicts" in warning for warning in result.warnings)


def test_halt_alert_penalises() -> None:
    result = check_consistency(
        make_technical(Direction.BULLISH),
        make_news(Sentiment.BULLISH, alert=AlertLevel.HALT_TRADING),
    )
    assert result.consistent is False
    assert result.confidence_penalty == pytest.approx(0.20)
    assert any("halt" in warning for warning in result.warnings)


def test_reduce_alert_uses_half_penalty() -> None:
    result = check_consistency(
        make_technical(Direction.BULLISH),
        make_news(Sentiment.BULLISH, alert=AlertLevel.REDUCE_POSITION_SIZE),
    )
    assert result.confidence_penalty == pytest.approx(0.10)


def test_neutral_news_does_not_conflict() -> None:
    result = check_consistency(make_technical(Direction.BULLISH), make_news(Sentiment.NEUTRAL))
    assert result.consistent is True


def test_alignment_strong_when_three_of_four_agree() -> None:
    alignment = TimeframeAlignment(aligned=3, total=4)
    assert alignment.strong is True


def test_alignment_weak_when_two_of_four_agree() -> None:
    alignment = TimeframeAlignment(aligned=2, total=4)
    assert alignment.strong is False


def test_single_timeframe_is_always_strong() -> None:
    assert TimeframeAlignment(aligned=1, total=1).strong is True


def test_confirm_timeframes_counts_directional_agreement() -> None:
    primary = make_technical(Direction.BULLISH)
    signals = {
        Timeframe.H4: make_technical(Direction.BULLISH),
        Timeframe.H1: primary,
        Timeframe.M15: make_technical(Direction.BEARISH),
    }
    alignment = confirm_timeframes(signals, primary)
    assert alignment.aligned == 2
    assert alignment.total == 3
    assert alignment.strong is False


def test_confirm_timeframes_ignores_neutral_signals() -> None:
    primary = make_technical(Direction.BULLISH)
    signals = {
        Timeframe.H4: make_technical(Direction.NEUTRAL),
        Timeframe.H1: primary,
    }
    alignment = confirm_timeframes(signals, primary)
    assert alignment.aligned == 1
    assert alignment.total == 1
    assert alignment.strong is True
