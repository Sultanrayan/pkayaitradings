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


# --------------------------------------------------------------------------- #
# record_signal — single records outside a cycle
# --------------------------------------------------------------------------- #


def test_record_signal_appends_one_record() -> None:
    store = SignalStore()
    record = store.record_signal(
        symbol="xauusd",
        correlation_id="c9",
        agent="decision_maker",
        kind="trade_decision",
        direction="BUY",
        confidence=0.6,
        payload={"outcome": "ADJUST"},
    )
    assert store.size == 1
    assert record.symbol == "XAUUSD"
    assert record.agent == "decision_maker"
    assert record.kind == "trade_decision"
    assert record.direction == "BUY"


def test_record_signal_is_queryable_and_does_not_disturb_the_cycle() -> None:
    store = SignalStore()
    _record(store)
    # An agent outside the four-agent cycle, so the query below cannot collide
    # with the records ``_record`` already wrote for each cycle agent.
    store.record_signal(
        symbol="XAUUSD",
        correlation_id="c1",
        agent="orchestrator",
        kind="order_fill",
        direction="BUY",
        confidence=0.5,
        payload={},
    )
    assert store.size == 5
    found = store.query(agent="orchestrator")
    assert len(found) == 1
    assert found[0].direction == "BUY"


def test_record_signal_respects_the_record_cap() -> None:
    store = SignalStore(max_records=3)
    for index in range(5):
        store.record_signal(
            symbol="XAUUSD",
            correlation_id=f"c{index}",
            agent="orchestrator",
            kind="order_fill",
            direction="BUY",
            confidence=0.5,
            payload={},
        )
    assert store.size == 3
    # The oldest were evicted, so the newest survives.
    assert store.query(limit=10)[0].correlation_id == "c4"


def test_the_agent_roster_is_exactly_four_agents() -> None:
    """The Signal Updater was removed; four agents remain.

    The roster is the contract behind ``GET /api/v1/agents``, so the count is
    asserted rather than left implicit.
    """
    store = SignalStore()
    status = {entry["name"]: entry for entry in store.agent_status()}
    assert set(status) == {
        "technical_analyst",
        "news_monitor",
        "risk_manager",
        "decision_maker",
    }
    assert "signal_updater" not in status


def test_an_agent_becomes_active_when_it_records_a_signal() -> None:
    """Roster wiring still works after the removal; exercised on the decision maker."""
    store = SignalStore()
    status = {entry["name"]: entry for entry in store.agent_status()}
    assert status["decision_maker"]["status"] == "idle"

    store.record_signal(
        symbol="XAUUSD",
        correlation_id="c1",
        agent="decision_maker",
        kind="trade_decision",
        direction="BUY",
        confidence=0.8,
        payload={},
    )
    status = {entry["name"]: entry for entry in store.agent_status()}
    assert status["decision_maker"]["signal_count"] == 1
    assert status["decision_maker"]["status"] == "active"
    assert status["decision_maker"]["avg_confidence"] == 0.8


# --------------------------------------------------------------------------- #
# latest_decision — seeding the Signal Updater
# --------------------------------------------------------------------------- #


def test_latest_decision_returns_the_newest_decision() -> None:
    store = SignalStore()
    _record(store)
    _record(store, decision=_decision(decision=Decision.SELL))
    found = store.latest_decision("XAUUSD")
    assert found is not None
    assert found.decision is Decision.SELL


def test_latest_decision_is_symbol_scoped() -> None:
    store = SignalStore()
    _record(store)
    assert store.latest_decision("BTCUSD") is None


def test_latest_decision_is_case_insensitive() -> None:
    store = SignalStore()
    _record(store)
    assert store.latest_decision("xauusd") is not None


def test_latest_decision_returns_none_on_an_empty_store() -> None:
    assert SignalStore().latest_decision("XAUUSD") is None


def test_latest_decision_skips_an_unreadable_payload() -> None:
    """A payload from an older schema must not break the updater's startup."""
    store = SignalStore()
    _record(store)
    store.record_signal(
        symbol="XAUUSD",
        correlation_id="c1",
        agent="decision_maker",
        kind="trade_decision",
        direction="BUY",
        confidence=0.5,
        payload={"decision": "BUY"},  # missing every required field
    )
    found = store.latest_decision("XAUUSD")
    assert found is not None
    assert found.decision is Decision.BUY


def test_latest_decision_ignores_non_decision_kinds() -> None:
    store = SignalStore()
    store.record_signal(
        symbol="XAUUSD",
        correlation_id="c1",
        agent="decision_maker",
        kind="trade_decision",
        direction="BUY",
        confidence=0.5,
        payload={},
    )
    assert store.latest_decision("XAUUSD") is None
