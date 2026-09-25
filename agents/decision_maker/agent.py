"""Decision Maker agent.

Aggregates the technical, news and risk outputs into a final trade decision and,
when an executor is supplied, hands approved trades to the execution layer.

Per the backend-v2 roadmap the Decision Maker also applies:

* a **cross-agent consistency check** (Problem 3) that downgrades conflicting
  technical/news views,
* **regime-aware adaptive weighting** (Problem 4),
* **non-linear aggregation** — weighted geometric mean with hard rules
  (Problem 5) — when ``decision_aggregation == "geometric"``,
* **multi-timeframe confirmation** (Problem 6) that penalises a primary signal
  contradicted by the other timeframes,
* an **order-flow absorption penalty** (Problem 7),
* **episodic-memory recall** that adjusts confidence by historical win rate
  (Problem 8),
* an **LLM chain-of-thought review** with a bounded confidence adjustment
  (Problem 10).
"""

from __future__ import annotations

import uuid
from typing import Any, Protocol, runtime_checkable

from agents.base_agent import BaseAgent
from agents.decision_maker.llm_reasoner import (
    DecisionReasoner,
    DecisionReview,
    build_reasoner,
)
from agents.decision_maker.voting_logic import (
    combine,
    combine_nonlinear,
    decide,
    score_news,
    score_risk,
    score_technical,
)
from shared.cross_checks import TimeframeAlignment, check_consistency
from shared.episodic_memory import (
    Episode,
    EpisodicMemory,
    MemoryRecall,
    build_episodic_memory,
)
from shared.order_flow import OrderFlowSignal
from shared.regime import MarketRegime, adaptive_weights
from shared.schemas.enums import AgentName, Decision, Direction
from shared.schemas.messages import Fill
from shared.schemas.signals import (
    NewsSignal,
    RiskAssessment,
    TechnicalSignal,
    TradeDecision,
)

_MAX_TOTAL_PENALTY = 0.25
_MTF_PENALTY = 0.10
_ORDER_FLOW_PENALTY = 0.10
_ORDER_FLOW_MIN_SCORE = 0.30


@runtime_checkable
class TradeExecutor(Protocol):
    """Minimal execution interface consumed by the Decision Maker."""

    async def execute(
        self,
        *,
        symbol: str,
        direction: Any,
        quantity: float,
        price: float | None = None,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> Fill:
        """Submit an order and return the resulting fill."""


class DecisionMakerAgent(BaseAgent):
    """Produces the final trade decision and optionally executes it.

    Args:
        executor: Optional execution adapter. When omitted, decisions are
            reported but not traded.
        reasoner: Optional rationale generator.
        memory: Optional episodic memory. Defaults to one built from settings.
        bus: Optional message bus.
        settings: Optional settings override.
    """

    name = AgentName.DECISION_MAKER

    def __init__(
        self,
        *,
        executor: TradeExecutor | None = None,
        reasoner: DecisionReasoner | None = None,
        memory: EpisodicMemory | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.executor = executor
        self.reasoner = reasoner or build_reasoner(self.settings)
        self.memory = memory or (
            build_episodic_memory(self.settings) if self.settings.episodic_memory_enabled else None
        )

    async def decide(
        self,
        technical: TechnicalSignal,
        news: NewsSignal,
        risk: RiskAssessment,
        *,
        regime: MarketRegime | None = None,
        mtf: TimeframeAlignment | None = None,
        order_flow: OrderFlowSignal | None = None,
    ) -> TradeDecision:
        """Combine the three signals into a :class:`TradeDecision`."""
        if regime is not None:
            weight_technical, weight_news, weight_risk = adaptive_weights(regime).as_tuple()
        else:
            weight_technical = self.settings.weight_technical
            weight_news = self.settings.weight_news
            weight_risk = self.settings.weight_risk

        cross = check_consistency(technical, news)
        mtf_penalty = _mtf_penalty(technical, mtf)
        order_flow_penalty = _order_flow_penalty(technical, order_flow)

        recall = MemoryRecall(samples=0, win_rate=None, adjustment=0.0)
        if self.memory is not None:
            recall = await self.memory.recall(_episode_features(technical, news, risk, regime))

        effective_confidence = _clamp01(
            technical.confidence
            - min(
                _MAX_TOTAL_PENALTY,
                cross.confidence_penalty + mtf_penalty + order_flow_penalty,
            )
            + recall.adjustment
        )

        tech_score = score_technical(technical.signal, effective_confidence)
        news_score = score_news(news.sentiment, news.confidence)
        risk_score = score_risk(risk.approved)

        if self.settings.decision_aggregation == "geometric":
            breakdown = combine_nonlinear(
                tech_score,
                news_score,
                risk_score,
                weight_technical=weight_technical,
                weight_news=weight_news,
                weight_risk=weight_risk,
            )
        else:
            breakdown = combine(
                tech_score,
                news_score,
                risk_score,
                weight_technical=weight_technical,
                weight_news=weight_news,
                weight_risk=weight_risk,
            )

        context: dict[str, Any] = {
            "symbol": technical.symbol,
            "technical_direction": technical.signal.value,
            "technical_confidence": effective_confidence,
            "news_sentiment": news.sentiment.value,
            "risk_approved": risk.approved,
            "risk_reasoning": risk.reasoning,
            "regime": regime.value if regime else "unknown",
            "aggregation": self.settings.decision_aggregation,
            "warnings": list(cross.warnings),
            "mtf_alignment": f"{mtf.aligned}/{mtf.total}" if mtf else "n/a",
            "order_flow": (
                f"{order_flow.direction.value} ({order_flow.score:+.2f})"
                if order_flow
                else "n/a"
            ),
            "memory_win_rate": recall.win_rate,
            "final_score": breakdown.final_score,
        }

        review = DecisionReview()
        if self.settings.llm_review_enabled:
            review = await self.reasoner.review(context)
        adjusted_score = _clamp01(breakdown.final_score + review.confidence_adjustment)

        decision = decide(
            adjusted_score,
            technical.signal,
            approved=risk.approved,
            buy_threshold=self.settings.decision_buy_threshold,
            skip_threshold=self.settings.decision_skip_threshold,
        )
        context["decision"] = decision.value
        context["final_score"] = adjusted_score
        reasoning = await self.reasoner.explain(context)

        executable = decision in {Decision.BUY, Decision.SELL} and risk.position_size > 0
        order_id: str | None = None
        executed = False
        if executable and self.executor is not None:
            fill = await self.executor.execute(
                symbol=technical.symbol,
                direction=technical.signal,
                quantity=risk.position_size,
                price=technical.price,
                stop_loss=risk.stop_loss,
                take_profit=risk.take_profit,
            )
            order_id = fill.order_id
            executed = True

        self.log.info(
            "decision_maker.decision",
            symbol=technical.symbol,
            decision=decision.value,
            final_score=adjusted_score,
            regime=regime.value if regime else "unknown",
            review_adjustment=review.confidence_adjustment,
            memory_adjustment=recall.adjustment,
            executed=executed,
        )
        return TradeDecision(
            symbol=technical.symbol,
            decision=decision,
            final_score=round(adjusted_score, 4),
            technical_score=breakdown.technical_score,
            news_score=breakdown.news_score,
            risk_score=breakdown.risk_score,
            risk_approved=risk.approved,
            position_size=risk.position_size if decision in {Decision.BUY, Decision.SELL} else 0.0,
            entry_price=technical.price,
            stop_loss=risk.stop_loss,
            take_profit=risk.take_profit,
            reasoning=reasoning,
            executed=executed,
            order_id=order_id,
        )

    async def run(
        self,
        technical: TechnicalSignal,
        news: NewsSignal,
        risk: RiskAssessment,
        *,
        regime: MarketRegime | None = None,
        mtf: TimeframeAlignment | None = None,
        order_flow: OrderFlowSignal | None = None,
        correlation_id: str | None = None,
    ) -> TradeDecision:
        """Decide and publish the resulting decision."""
        decision = await self._guarded(
            TradeDecision,
            self.decide,
            technical,
            news,
            risk,
            regime=regime,
            mtf=mtf,
            order_flow=order_flow,
        )
        if self.memory is not None:
            await self.memory.record(
                Episode(
                    correlation_id=correlation_id or uuid.uuid4().hex,
                    symbol=technical.symbol,
                    features=_episode_features(technical, news, risk, regime),
                    decision=decision.decision.value,
                )
            )
        await self.publish(decision, kind="trade_decision", correlation_id=correlation_id)
        return decision


def _mtf_penalty(
    technical: TechnicalSignal, mtf: TimeframeAlignment | None
) -> float:
    """Penalty for a primary direction contradicted by the other timeframes."""
    if mtf is None or technical.signal is Direction.NEUTRAL or mtf.strong:
        return 0.0
    return _MTF_PENALTY


def _order_flow_penalty(
    technical: TechnicalSignal, order_flow: OrderFlowSignal | None
) -> float:
    """Penalty when order-flow absorption opposes the primary direction."""
    if (
        order_flow is None
        or technical.signal is Direction.NEUTRAL
        or order_flow.direction is Direction.NEUTRAL
        or abs(order_flow.score) < _ORDER_FLOW_MIN_SCORE
    ):
        return 0.0
    opposing = (
        technical.signal is Direction.BULLISH and order_flow.direction is Direction.BEARISH
    ) or (
        technical.signal is Direction.BEARISH and order_flow.direction is Direction.BULLISH
    )
    if not opposing:
        return 0.0
    return min(_ORDER_FLOW_PENALTY, abs(order_flow.score) * _ORDER_FLOW_PENALTY)


def _episode_features(
    technical: TechnicalSignal,
    news: NewsSignal,
    risk: RiskAssessment,
    regime: MarketRegime | None,
) -> dict[str, float]:
    """Numeric situation features used to recall similar past episodes."""
    price = technical.price or 1.0
    return {
        "direction": technical.signal.score,
        "confidence": technical.confidence,
        "rsi": (technical.indicators.rsi or 50.0) / 100.0,
        "adx": (technical.indicators.adx or 0.0) / 60.0,
        "atr_pct": (technical.indicators.atr or 0.0) / price,
        "news_sentiment": news.sentiment.score,
        "news_confidence": news.confidence,
        "risk_approved": 1.0 if risk.approved else 0.0,
        "regime": (
            {MarketRegime.TRENDING: 1.0, MarketRegime.SIDEWAYS: 0.5, MarketRegime.VOLATILE: 0.0}[
                regime
            ]
            if regime
            else 0.5
        ),
    }


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))
