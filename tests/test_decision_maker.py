"""Tests for the Decision Maker's voting logic and agent."""

from __future__ import annotations

import pytest

from agents.decision_maker.agent import DecisionMakerAgent
from agents.decision_maker.llm_reasoner import DecisionReview
from agents.decision_maker.voting_logic import (
    combine,
    combine_nonlinear,
    decide,
    score_news,
    score_risk,
    score_technical,
)
from shared.config import Settings
from shared.cross_checks import TimeframeAlignment
from shared.episodic_memory import MemoryRecall
from shared.order_flow import OrderFlowSignal
from shared.regime import MarketRegime
from shared.schemas.enums import Decision, Direction, Sentiment, Timeframe
from shared.schemas.messages import Fill, OrderSide
from shared.schemas.signals import NewsSignal, RiskAssessment, TechnicalSignal


def make_technical(
    direction: Direction = Direction.BULLISH, confidence: float = 0.9
) -> TechnicalSignal:
    return TechnicalSignal(
        symbol="XAUUSD",
        timeframe=Timeframe.H1,
        signal=direction,
        confidence=confidence,
        price=2650.0,
    )


def make_news(sentiment: Sentiment = Sentiment.BULLISH, confidence: float = 0.8) -> NewsSignal:
    return NewsSignal(event="FOMC", sentiment=sentiment, confidence=confidence)


def make_risk(approved: bool = True, size: float = 1.5) -> RiskAssessment:
    return RiskAssessment(symbol="XAUUSD", approved=approved, position_size=size)


def test_score_technical_directions() -> None:
    assert score_technical(Direction.BULLISH, 0.8) == 0.8
    assert score_technical(Direction.BEARISH, 0.8) == pytest.approx(0.2)
    assert score_technical(Direction.NEUTRAL, 0.8) == 0.5


def test_score_news_shrinks_toward_neutral() -> None:
    assert score_news(Sentiment.VERY_BULLISH, 1.0) == 1.0
    assert score_news(Sentiment.NEUTRAL, 1.0) == 0.5
    assert score_news(Sentiment.VERY_BULLISH, 0.0) == 0.5


def test_score_risk() -> None:
    assert score_risk(True) == 1.0
    assert score_risk(False) == 0.0


def test_combine_requires_normalised_weights() -> None:
    with pytest.raises(ValueError, match=r"sum to 1\.0"):
        combine(1, 1, 1, weight_technical=0.5, weight_news=0.5, weight_risk=0.5)


def test_combine_weighted_average() -> None:
    breakdown = combine(1.0, 0.5, 1.0, weight_technical=0.45, weight_news=0.25, weight_risk=0.30)
    assert breakdown.final_score == pytest.approx(0.875)


def test_combine_nonlinear_veto_collapses_score() -> None:
    breakdown = combine_nonlinear(
        0.9, 0.7, 0.0, weight_technical=0.45, weight_news=0.25, weight_risk=0.30
    )
    assert breakdown.final_score == 0.0


def test_combine_nonlinear_disagreement_cap() -> None:
    breakdown = combine_nonlinear(
        0.39, 1.0, 1.0, weight_technical=0.45, weight_news=0.25, weight_risk=0.30
    )
    assert breakdown.final_score == pytest.approx(0.50)


def test_combine_nonlinear_aligned_strong_unchanged() -> None:
    breakdown = combine_nonlinear(
        0.9, 0.7, 1.0, weight_technical=0.45, weight_news=0.25, weight_risk=0.30
    )
    expected = round(0.9**0.45 * 0.7**0.25, 4)
    assert breakdown.final_score == pytest.approx(expected)


def test_combine_nonlinear_requires_normalised_weights() -> None:
    with pytest.raises(ValueError, match=r"sum to 1\.0"):
        combine_nonlinear(1, 1, 1, weight_technical=0.5, weight_news=0.5, weight_risk=0.5)


def test_decide_veto_forces_skip() -> None:
    assert (
        decide(0.99, Direction.BULLISH, approved=False, buy_threshold=0.65, skip_threshold=0.35)
        is Decision.SKIP
    )


def test_decide_buy() -> None:
    assert (
        decide(0.8, Direction.BULLISH, approved=True, buy_threshold=0.65, skip_threshold=0.35)
        is Decision.BUY
    )


def test_decide_sell() -> None:
    assert (
        decide(0.2, Direction.BEARISH, approved=True, buy_threshold=0.65, skip_threshold=0.35)
        is Decision.SELL
    )


def test_decide_never_waits() -> None:
    """The middle band used to return WAIT. It is now the primary direction.

    A score of 0.50 between the thresholds is a coin flip, and the honest
    response to a coin flip at small size is a quarter-size position — not a
    refusal that leaves the decision to nobody.
    """
    assert (
        decide(0.5, Direction.BULLISH, approved=True, buy_threshold=0.65, skip_threshold=0.35)
        is Decision.BUY
    )


def test_decide_never_waits_on_a_bearish_read_either() -> None:
    assert (
        decide(0.5, Direction.BEARISH, approved=True, buy_threshold=0.65, skip_threshold=0.35)
        is Decision.SELL
    )


def test_a_strong_aggregate_does_not_flip_a_bearish_primary() -> None:
    """The aggregate sets conviction, not direction.

    The Risk Manager has already priced the stop and target for the technical
    read. Flipping the action on score would emit a BUY carrying a stop above
    entry — an unbounded-loss order wearing a bullish label. This test was written
    after a live cycle produced exactly that.
    """
    assert (
        decide(0.9, Direction.BEARISH, approved=True, buy_threshold=0.65, skip_threshold=0.35)
        is Decision.SELL
    )


def test_a_weak_aggregate_does_not_flip_a_bullish_primary() -> None:
    assert (
        decide(0.1, Direction.BULLISH, approved=True, buy_threshold=0.65, skip_threshold=0.35)
        is Decision.BUY
    )


def test_a_bullish_primary_stays_buy_across_the_score_range() -> None:
    for score in (0.0, 0.35, 0.65, 1.0):
        assert (
            decide(
                score,
                Direction.BULLISH,
                approved=True,
                buy_threshold=0.65,
                skip_threshold=0.35,
            )
            is Decision.BUY
        )


def test_a_drawdown_veto_still_skips() -> None:
    """The one non-actionable outcome, and it is deliberate.

    ``approved=False`` means the portfolio drawdown limit was breached. That is a
    loss-limiting control, not a view on the market, so it is not converted into
    a smaller position.
    """
    assert (
        decide(0.95, Direction.BULLISH, approved=False, buy_threshold=0.65, skip_threshold=0.35)
        is Decision.SKIP
    )
    assert (
        decide(0.05, Direction.BEARISH, approved=False, buy_threshold=0.65, skip_threshold=0.35)
        is Decision.SKIP
    )


@pytest.mark.parametrize("score", [0.0, 0.01, 0.2, 0.35, 0.5, 0.65, 0.8, 0.99, 1.0])
@pytest.mark.parametrize("direction", [Direction.BULLISH, Direction.BEARISH])
def test_decide_is_actionable_across_the_whole_score_range(
    score: float, direction: Direction
) -> None:
    """Swept across scores and both directions: never WAIT, never SKIP on a
    cleared trade."""
    result = decide(
        score, direction, approved=True, buy_threshold=0.65, skip_threshold=0.35
    )
    assert result in {Decision.BUY, Decision.SELL}


class _StubExecutor:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def execute(self, **kwargs: object) -> Fill:
        self.calls.append(kwargs)
        return Fill(
            order_id="order-1",
            symbol=str(kwargs["symbol"]),
            side=OrderSide.BUY,
            quantity=float(kwargs["quantity"]),  # type: ignore[arg-type]
            price=2650.0,
        )


async def test_decision_agent_executes_approved_trade() -> None:
    executor = _StubExecutor()
    agent = DecisionMakerAgent(executor=executor)
    decision = await agent.decide(make_technical(), make_news(), make_risk())
    assert decision.decision is Decision.BUY
    assert decision.executed is True
    assert decision.order_id == "order-1"
    assert len(executor.calls) == 1


async def test_decision_agent_does_not_execute_on_veto() -> None:
    executor = _StubExecutor()
    agent = DecisionMakerAgent(executor=executor)
    decision = await agent.decide(make_technical(), make_news(), make_risk(approved=False))
    assert decision.decision is Decision.SKIP
    assert decision.executed is False
    assert executor.calls == []


async def test_decision_agent_without_executor_does_not_trade() -> None:
    agent = DecisionMakerAgent()
    decision = await agent.decide(make_technical(), make_news(), make_risk())
    assert decision.decision is Decision.BUY
    assert decision.executed is False


async def test_decision_agent_applies_regime_and_mtf_penalties() -> None:
    agent = DecisionMakerAgent()
    decision = await agent.decide(
        make_technical(),
        make_news(),
        make_risk(),
        regime=MarketRegime.SIDEWAYS,
        mtf=TimeframeAlignment(aligned=1, total=3),
    )
    assert decision.decision is Decision.BUY
    assert decision.technical_score == pytest.approx(0.8)


async def test_decision_agent_weighted_aggregation_mode() -> None:
    agent = DecisionMakerAgent(settings=Settings(decision_aggregation="weighted"))
    decision = await agent.decide(make_technical(), make_news(), make_risk())
    assert decision.decision is Decision.BUY
    assert decision.final_score == pytest.approx(0.45 * 0.9 + 0.25 * 0.7 + 0.30 * 1.0)


async def test_decision_agent_applies_order_flow_penalty() -> None:
    agent = DecisionMakerAgent()
    flow = OrderFlowSignal(
        direction=Direction.BEARISH, score=0.8, delta=0.8, divergence=0.0, exhaustion=0.0
    )
    decision = await agent.decide(make_technical(), make_news(), make_risk(), order_flow=flow)
    assert decision.technical_score == pytest.approx(0.82)


class _StubMemory:
    def __init__(self, adjustment: float, win_rate: float | None) -> None:
        self.adjustment = adjustment
        self.win_rate = win_rate
        self.recorded: list[object] = []

    async def recall(self, features: dict[str, float], *, k: int | None = None, min_samples: int | None = None) -> MemoryRecall:
        return MemoryRecall(samples=8, win_rate=self.win_rate, adjustment=self.adjustment)

    async def record(self, episode: object) -> None:
        self.recorded.append(episode)


async def test_decision_agent_applies_memory_adjustment() -> None:
    agent = DecisionMakerAgent(memory=_StubMemory(adjustment=-0.10, win_rate=0.2))  # type: ignore[arg-type]
    decision = await agent.decide(make_technical(), make_news(), make_risk())
    assert decision.technical_score == pytest.approx(0.8)


class _ReviewingReasoner:
    def __init__(self, review: DecisionReview) -> None:
        self._review = review

    async def explain(self, context: dict[str, object]) -> str:
        return "reviewed"

    async def review(self, context: dict[str, object]) -> DecisionReview:
        return self._review


async def test_decision_agent_applies_llm_review_adjustment() -> None:
    review = DecisionReview(consistent=True, confidence_adjustment=0.10)
    agent = DecisionMakerAgent(reasoner=_ReviewingReasoner(review))
    decision = await agent.decide(make_technical(), make_news(), make_risk())
    expected = round(0.9**0.45 * 0.7**0.25 * 1.0**0.30 + 0.10, 4)
    assert decision.final_score == pytest.approx(expected)


async def test_decision_agent_records_episodes_on_run() -> None:
    memory = _StubMemory(adjustment=0.0, win_rate=None)
    agent = DecisionMakerAgent(memory=memory)  # type: ignore[arg-type]
    await agent.run(make_technical(), make_news(), make_risk())
    assert len(memory.recorded) == 1
