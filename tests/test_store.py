"""Tests for the in-memory signal store."""

from __future__ import annotations

from orchestrator.store import SignalStore
from shared.schemas.enums import (
    AlertLevel,
    Decision,
    Direction,
    Impact,
    Sentiment,
    Timeframe,
)
from shared.schemas.signals import (
    NewsSignal,
    RiskAssessment,
    TechnicalSignal,
    TradeDecision,
)


def _technical(
    direction: Direction = Direction.BULLISH, confidence: float = 0.8
) -> TechnicalSignal:
    return TechnicalSignal(
        symbol="XAUUSD", timeframe=Timeframe.H1, signal=direction, confidence=confidence
    )


def _news(
    sentiment: Sentiment = Sentiment.BULLISH, alert: AlertLevel = AlertLevel.NONE
) -> NewsSignal:
    return NewsSignal(
        event="FOMC", impact=Impact.HIGH, sentiment=sentiment, confidence=0.7, alert=alert
    )


def _risk(approved: bool = True) -> RiskAssessment:
    return RiskAssessment(symbol="XAUUSD", approved=approved, position_size=1.0)


def _decision(decision: Decision = Decision.BUY, executed: bool = True) -> TradeDecision:
    return TradeDecision(
        symbol="XAUUSD",
        decision=decision,
        final_score=0.8,
        technical_score=0.8,
        news_score=0.7,
        risk_score=1.0,
        risk_approved=True,
        executed=executed,
    )


def _record(store: SignalStore, **overrides: object) -> None:
    store.record_cycle(
        symbol="XAUUSD",
        correlation_id="c1",
        technical=overrides.get("technical", _technical()),  # type: ignore[arg-type]
        news=overrides.get("news", _news()),  # type: ignore[arg-type]
        risk=overrides.get("risk", _risk()),  # type: ignore[arg-type]
        decision=overrides.get("decision", _decision()),  # type: ignore[arg-type]
    )


def test_record_cycle_adds_four_signals() -> None:
    store = SignalStore()
    _record(store)
    assert store.size == 4
    agents = {record.agent for record in store.query(limit=10)}
    assert agents == {
        "technical_analyst",
        "news_monitor",
        "risk_manager",
        "decision_maker",
    }


def test_query_filters_by_symbol_agent_direction_and_confidence() -> None:
    store = SignalStore()
    _record(store)

    assert len(store.query(symbol="XAUUSD")) == 4
    assert len(store.query(agent="technical_analyst")) == 1
    assert len(store.query(direction="BULLISH")) == 2  # technical + news
    assert len(store.query(min_confidence=0.9)) == 1  # risk score 1.0
    assert store.query(symbol="BTCUSD") == []
    assert len(store.query(limit=2)) == 2


def test_latest_cycle_returns_matching_records() -> None:
    store = SignalStore()
    _record(store)
    latest = store.latest_cycle("XAUUSD")
    assert len(latest) == 4
    assert store.latest_cycle("BTCUSD") == []


def test_agent_status_reports_active() -> None:
    store = SignalStore()
    _record(store)
    statuses = {entry["name"]: entry for entry in store.agent_status()}
    assert statuses["technical_analyst"]["status"] == "active"
    assert statuses["technical_analyst"]["signal_count"] == 1
    assert statuses["news_monitor"]["last_signal_at"] is not None


def test_agent_status_idle_when_empty() -> None:
    statuses = {entry["name"]: entry for entry in SignalStore().agent_status()}
    assert statuses["decision_maker"]["status"] == "idle"
    assert statuses["decision_maker"]["signal_count"] == 0


def test_stats_aggregates() -> None:
    store = SignalStore()
    _record(store)
    stats = store.stats()
    assert stats["total_signals"] == 4
    assert stats["bullish"] == 2
    assert stats["bearish"] == 0
    assert stats["decisions"]["BUY"] == 1
    assert stats["by_symbol"]["XAUUSD"]["count"] == 4
    assert "technical_analyst" in stats["by_agent"]
    assert len(stats["activity_by_hour"]) == 24
    assert sum(stats["confidence_buckets"]) == 4


def test_alerts_include_news_risk_and_decision() -> None:
    store = SignalStore()
    _record(
        store,
        news=_news(alert=AlertLevel.HALT_TRADING),
        risk=_risk(approved=False),
    )
    alerts = store.alerts()
    types = {alert["type"] for alert in alerts}
    assert {"news", "risk", "decision"} <= types
    assert any(alert["priority"] == "critical" for alert in alerts)


def test_alerts_empty_for_quiet_cycle() -> None:
    store = SignalStore()
    _record(store, decision=_decision(executed=False))
    assert store.alerts() == []
