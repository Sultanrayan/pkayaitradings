"""In-memory signal store backing the dashboard and analytics endpoints.

Every analysis cycle records its four agent outputs here. The store is
process-local and bounded; it is intentionally simple and dependency-free so the
UI works without PostgreSQL. When the database layer is enabled, the same
records are persisted by the repository module.
"""

from __future__ import annotations

import uuid
from collections import Counter, deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from shared.schemas.enums import AgentName, Decision, Direction, Sentiment
from shared.schemas.signals import (
    NewsSignal,
    RiskAssessment,
    TechnicalSignal,
    TradeDecision,
)
from shared.utils.time import utcnow

_SENTIMENT_DIRECTION: dict[Sentiment, Direction] = {
    Sentiment.VERY_BULLISH: Direction.BULLISH,
    Sentiment.BULLISH: Direction.BULLISH,
    Sentiment.NEUTRAL: Direction.NEUTRAL,
    Sentiment.BEARISH: Direction.BEARISH,
    Sentiment.VERY_BEARISH: Direction.BEARISH,
}

_AGENT_ORDER: tuple[str, ...] = (
    AgentName.TECHNICAL_ANALYST.value,
    AgentName.NEWS_MONITOR.value,
    AgentName.RISK_MANAGER.value,
    AgentName.DECISION_MAKER.value,
)


@dataclass(frozen=True)
class SignalRecord:
    """A single agent signal captured during a cycle."""

    id: str
    correlation_id: str
    symbol: str
    agent: str
    kind: str
    direction: str
    confidence: float
    created_at: datetime
    payload: dict[str, Any] = field(default_factory=dict)


class SignalStore:
    """Bounded, in-memory record of agent signals.

    Args:
        max_records: Maximum records retained (oldest evicted first).
    """

    def __init__(self, max_records: int = 5_000) -> None:
        self._records: deque[SignalRecord] = deque(maxlen=max_records)

    # ------------------------------------------------------------------ #
    # Writing
    # ------------------------------------------------------------------ #
    def record_cycle(
        self,
        *,
        symbol: str,
        correlation_id: str,
        technical: TechnicalSignal,
        news: NewsSignal,
        risk: RiskAssessment,
        decision: TradeDecision,
    ) -> None:
        """Record the four agent outputs from one cycle."""
        now = utcnow()
        self._records.extend(
            [
                self._make(
                    symbol,
                    correlation_id,
                    AgentName.TECHNICAL_ANALYST.value,
                    "technical_signal",
                    technical.signal.value,
                    technical.confidence,
                    technical.model_dump(mode="json"),
                    now,
                ),
                self._make(
                    symbol,
                    correlation_id,
                    AgentName.NEWS_MONITOR.value,
                    "news_signal",
                    _SENTIMENT_DIRECTION[news.sentiment].value,
                    news.confidence,
                    news.model_dump(mode="json"),
                    now,
                ),
                self._make(
                    symbol,
                    correlation_id,
                    AgentName.RISK_MANAGER.value,
                    "risk_assessment",
                    "APPROVED" if risk.approved else "VETO",
                    1.0 if risk.approved else 0.0,
                    risk.model_dump(mode="json"),
                    now,
                ),
                self._make(
                    symbol,
                    correlation_id,
                    AgentName.DECISION_MAKER.value,
                    "trade_decision",
                    decision.decision.value,
                    decision.final_score,
                    decision.model_dump(mode="json"),
                    now,
                ),
            ]
        )

    @staticmethod
    def _make(
        symbol: str,
        correlation_id: str,
        agent: str,
        kind: str,
        direction: str,
        confidence: float,
        payload: dict[str, Any],
        created_at: datetime,
    ) -> SignalRecord:
        return SignalRecord(
            id=uuid.uuid4().hex,
            correlation_id=correlation_id,
            symbol=symbol,
            agent=agent,
            kind=kind,
            direction=direction,
            confidence=confidence,
            created_at=created_at,
            payload=payload,
        )

    # ------------------------------------------------------------------ #
    # Reading
    # ------------------------------------------------------------------ #
    @property
    def size(self) -> int:
        """Number of retained records."""
        return len(self._records)

    def query(
        self,
        *,
        symbol: str | None = None,
        agent: str | None = None,
        direction: str | None = None,
        min_confidence: float | None = None,
        limit: int = 100,
    ) -> list[SignalRecord]:
        """Return records (newest first) matching the given filters."""
        selected: list[SignalRecord] = []
        for record in reversed(self._records):
            if symbol and record.symbol != symbol.upper():
                continue
            if agent and record.agent != agent:
                continue
            if direction and record.direction != direction.upper():
                continue
            if min_confidence is not None and record.confidence < min_confidence:
                continue
            selected.append(record)
            if len(selected) >= limit:
                break
        return selected

    def latest_cycle(self, symbol: str | None = None) -> list[SignalRecord]:
        """Return the most recent cycle's records (all agents)."""
        target: str | None = None
        for record in reversed(self._records):
            if symbol and record.symbol != symbol.upper():
                continue
            target = record.correlation_id
            break
        if target is None:
            return []
        return [record for record in self._records if record.correlation_id == target]

    def agent_status(self, *, active_window_seconds: int = 900) -> list[dict[str, Any]]:
        """Return per-agent status, heartbeat and aggregate metrics."""
        now = utcnow()
        summary: dict[str, dict[str, Any]] = {
            agent: {
                "name": agent,
                "status": "idle",
                "signal_count": 0,
                "avg_confidence": 0.0,
                "last_signal_at": None,
                "_confidence_sum": 0.0,
            }
            for agent in _AGENT_ORDER
        }
        for record in self._records:
            entry = summary.get(record.agent)
            if entry is None:
                continue
            entry["signal_count"] += 1
            entry["_confidence_sum"] += record.confidence
            if entry["last_signal_at"] is None or record.created_at > entry["last_signal_at"]:
                entry["last_signal_at"] = record.created_at

        results: list[dict[str, Any]] = []
        for agent in _AGENT_ORDER:
            entry = summary[agent]
            count = entry["signal_count"]
            entry["avg_confidence"] = round(entry["_confidence_sum"] / count, 4) if count else 0.0
            last = entry["last_signal_at"]
            if last is None:
                entry["status"] = "idle"
            else:
                age = (now - last).total_seconds()
                entry["status"] = "active" if age <= active_window_seconds else "idle"
                entry["last_signal_at"] = last.isoformat()
            entry.pop("_confidence_sum", None)
            results.append(entry)
        return results

    def stats(self) -> dict[str, Any]:
        """Aggregate statistics across all retained signals."""
        directions = Counter(
            record.direction
            for record in self._records
            if record.direction
            in {Direction.BULLISH.value, Direction.BEARISH.value, Direction.NEUTRAL.value}
        )
        decisions = Counter(
            record.direction for record in self._records if record.kind == "trade_decision"
        )
        confidence_values = [record.confidence for record in self._records]
        by_symbol: dict[str, dict[str, Any]] = {}
        by_agent: dict[str, dict[str, Any]] = {}
        buckets = [0] * 5
        activity = [0] * 24
        for record in self._records:
            symbol_entry = by_symbol.setdefault(
                record.symbol,
                {"count": 0, "bullish": 0, "bearish": 0, "neutral": 0, "_sum": 0.0},
            )
            symbol_entry["count"] += 1
            symbol_entry["_sum"] += record.confidence
            if record.direction == Direction.BULLISH.value:
                symbol_entry["bullish"] += 1
            elif record.direction == Direction.BEARISH.value:
                symbol_entry["bearish"] += 1
            elif record.direction == Direction.NEUTRAL.value:
                symbol_entry["neutral"] += 1

            agent_entry = by_agent.setdefault(record.agent, {"count": 0, "_sum": 0.0})
            agent_entry["count"] += 1
            agent_entry["_sum"] += record.confidence

            bucket = min(int(record.confidence * 5), 4)
            buckets[bucket] += 1
            activity[record.created_at.hour] += 1

        for entry in by_symbol.values():
            entry["avg_confidence"] = (
                round(entry["_sum"] / entry["count"], 4) if entry["count"] else 0.0
            )
            entry.pop("_sum", None)
        for entry in by_agent.values():
            entry["avg_confidence"] = (
                round(entry["_sum"] / entry["count"], 4) if entry["count"] else 0.0
            )
            entry.pop("_sum", None)

        return {
            "total_signals": len(self._records),
            "bullish": directions[Direction.BULLISH.value],
            "bearish": directions[Direction.BEARISH.value],
            "neutral": directions[Direction.NEUTRAL.value],
            "avg_confidence": round(sum(confidence_values) / len(confidence_values), 4)
            if confidence_values
            else 0.0,
            "decisions": {decision.value: decisions[decision.value] for decision in Decision},
            "by_symbol": by_symbol,
            "by_agent": by_agent,
            "confidence_buckets": buckets,
            "activity_by_hour": activity,
        }

    def alerts(self, *, limit: int = 50) -> list[dict[str, Any]]:
        """Derive user-facing alerts from recorded signals."""
        alerts: list[dict[str, Any]] = []
        for record in reversed(self._records):
            payload = record.payload
            if record.kind == "news_signal":
                alert = str(payload.get("alert", "NONE"))
                if alert == "NONE":
                    continue
                priority = "critical" if alert == "HALT_TRADING" else "high"
                alerts.append(
                    {
                        "id": record.id,
                        "type": "news",
                        "priority": priority,
                        "symbol": record.symbol,
                        "title": f"{alert.replace('_', ' ').title()} — {payload.get('event', 'event')}",
                        "detail": payload.get("reasoning", ""),
                        "created_at": record.created_at.isoformat(),
                    }
                )
            elif record.kind == "risk_assessment" and not payload.get("approved", True):
                alerts.append(
                    {
                        "id": record.id,
                        "type": "risk",
                        "priority": "critical",
                        "symbol": record.symbol,
                        "title": "Risk veto",
                        "detail": payload.get("reasoning", ""),
                        "created_at": record.created_at.isoformat(),
                    }
                )
            elif record.kind == "trade_decision" and payload.get("executed"):
                alerts.append(
                    {
                        "id": record.id,
                        "type": "decision",
                        "priority": "high",
                        "symbol": record.symbol,
                        "title": f"Order executed — {payload.get('decision')}",
                        "detail": payload.get("reasoning", ""),
                        "created_at": record.created_at.isoformat(),
                    }
                )
            if len(alerts) >= limit:
                break
        return alerts
