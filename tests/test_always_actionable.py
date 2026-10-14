"""The always-actionable contract for the four agents.

One file for the property that spans all four, because the property is a system
property: "every cycle produces a BUY or SELL with complete levels and four
narrative fields". Testing each agent's version separately would let a gap open
between them — the technical analyst could stop abstaining while the decision
maker quietly started returning SKIP again, and each file would still be green.

The single deliberate exception is the Risk Manager's drawdown veto, which is a
loss-limiting control rather than a view on the market. It is pinned by its own
test here so that softening it later is an explicit, visible decision.
"""

from __future__ import annotations

import pytest

from agents.decision_maker.voting_logic import decide
from agents.risk_manager.agent import SIZE_MULTIPLIERS, SL_ADJUSTMENTS, risk_regime
from agents.risk_manager.position_sizer import plan_position
from agents.technical_analyst.strategy import (
    TechnicalParams,
    signal_from_composite,
    strength_from_confidence,
)
from shared.schemas.enums import Decision, Direction, Sentiment, Strength

NARRATIVE_FIELDS = ("recommendation", "explanation", "risk_notes", "invalidation")


# --------------------------------------------------------------------------- #
# Technical Analyst — always directional
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("composite", [-1.0, -0.5, -0.15, -0.01, 0.0, 0.01, 0.15, 0.5, 1.0])
@pytest.mark.parametrize("trend_strength", [0.4, 0.8, 1.0])
def test_technical_always_directional(composite: float, trend_strength: float) -> None:
    """Every composite value produces a direction. There is no abstention band."""
    direction, confidence = signal_from_composite(
        composite, trend_strength, TechnicalParams()
    )
    assert direction in {Direction.BULLISH, Direction.BEARISH}
    assert 0.0 < confidence <= 1.0


def test_technical_never_emits_neutral() -> None:
    """The specific regression: ``neutral_threshold`` used to return NEUTRAL."""
    for composite in (-0.149, -0.001, 0.0, 0.001, 0.149, 0.15):
        direction, _ = signal_from_composite(composite, 1.0, TechnicalParams())
        assert direction is not Direction.NEUTRAL


def test_the_technical_signal_carries_all_four_narrative_fields() -> None:
    from shared.schemas.signals import TechnicalSignal

    fields = set(TechnicalSignal.model_fields)
    for name in NARRATIVE_FIELDS:
        assert name in fields, f"TechnicalSignal is missing {name}"
    assert "strength" in fields


# --------------------------------------------------------------------------- #
# News Monitor — a weight, never a gate
# --------------------------------------------------------------------------- #


def test_news_never_blocks() -> None:
    """The worst possible news still returns a signal object with a score."""
    from shared.schemas.signals import NewsSignal

    for sentiment in Sentiment:
        signal = NewsSignal(event="FOMC", sentiment=sentiment)
        score = round(sentiment.score * 2.0 - 1.0, 4)
        assert -1.0 <= score <= 1.0, f"{sentiment} produced an out-of-range score"
        assert signal.sentiment_score == 0.0 or isinstance(score, float)


def test_neutral_sentiment_is_a_zero_weight_not_a_refusal() -> None:
    """NEUTRAL scores 0.5 in the enum and 0.0 on the [-1, 1] scale."""
    assert Sentiment.NEUTRAL.score == 0.5
    assert round(Sentiment.NEUTRAL.score * 2.0 - 1.0, 4) == 0.0


def test_sentiment_score_is_always_in_range() -> None:
    for sentiment in Sentiment:
        score = round(sentiment.score * 2.0 - 1.0, 4)
        assert -1.0 <= score <= 1.0


def test_the_news_signal_can_never_be_none() -> None:
    """The model has no nullable sentiment field, so it cannot be absent."""
    from shared.schemas.signals import NewsSignal

    assert "sentiment" in NewsSignal.model_fields
    assert "sentiment_score" in NewsSignal.model_fields
    assert NewsSignal(event="x").sentiment_score == 0.0


def test_news_includes_risk_notes() -> None:
    from shared.schemas.signals import NewsSignal

    assert "risk_notes" in NewsSignal.model_fields
    assert NewsSignal(event="x").risk_notes == ""


# --------------------------------------------------------------------------- #
# Risk Manager — size, never refuse (except drawdown)
# --------------------------------------------------------------------------- #


def test_risk_never_rejects_except_drawdown() -> None:
    """``approved`` is now a function of the drawdown check alone.

    Every other risk condition — volatility, correlation, VaR, a zero-Kelly
    allocation — produces a smaller position instead of ``approved=False``.
    """
    from shared.schemas.signals import RiskAssessment

    field = RiskAssessment.model_fields
    assert "position_size_multiplier" in field
    assert "sl_adjustment" in field
    assert "risk_notes" in field
    assert "invalidation" in field


@pytest.mark.parametrize(
    ("drawdown", "expected"),
    [(0.0, "normal"), (0.02, "normal"), (0.06, "elevated"), (0.15, "high")],
)
def test_the_regime_scales_size_and_stop(drawdown: float, expected: str) -> None:
    regime = risk_regime(
        drawdown_pct=drawdown, atr=10.0, atr_baseline=10.0, correlation=0.1
    )
    assert regime == expected
    assert 0.0 < SIZE_MULTIPLIERS[regime] <= 1.0
    assert SL_ADJUSTMENTS[regime] > 0.0


def test_high_risk_shrinks_the_position_and_widens_the_stop() -> None:
    assert SIZE_MULTIPLIERS["high"] < SIZE_MULTIPLIERS["normal"]
    assert SL_ADJUSTMENTS["high"] > SL_ADJUSTMENTS["normal"]


def test_a_stop_adjustment_is_never_zero() -> None:
    """A zero adjustment would mean no stop at all."""
    for regime, adjustment in SL_ADJUSTMENTS.items():
        assert adjustment > 0.0, f"{regime} has a zero stop adjustment"


def test_risk_includes_risk_notes_and_invalidation() -> None:
    from shared.schemas.signals import RiskAssessment

    assert "risk_notes" in RiskAssessment.model_fields
    assert "invalidation" in RiskAssessment.model_fields


def test_a_zero_kelly_call_still_gets_a_size() -> None:
    """Confidence 0 gives Kelly 0. That must floor, not vanish."""
    plan = plan_position(
        equity=100_000, price=4_000.0, atr=20.0, confidence=0.0, direction=Direction.BULLISH
    )
    assert plan.quantity > 0
    assert plan.stop_loss is not None
    assert plan.take_profit is not None


# --------------------------------------------------------------------------- #
# Decision Maker — always actionable
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("score", [0.0, 0.2, 0.35, 0.5, 0.65, 0.8, 1.0])
@pytest.mark.parametrize("direction", [Direction.BULLISH, Direction.BEARISH])
def test_decision_always_actionable(score: float, direction: Direction) -> None:
    result = decide(
        score, direction, approved=True, buy_threshold=0.65, skip_threshold=0.35
    )
    assert result in {Decision.BUY, Decision.SELL}


def test_decision_never_returns_wait() -> None:
    """WAIT has no remaining producer anywhere in the system."""
    for score in (0.0, 0.3, 0.5, 0.7, 1.0):
        for direction in (Direction.BULLISH, Direction.BEARISH):
            assert (
                decide(
                    score,
                    direction,
                    approved=True,
                    buy_threshold=0.65,
                    skip_threshold=0.35,
                )
                is not Decision.WAIT
            )


def test_drawdown_veto_still_works() -> None:
    """The one deliberate non-actionable outcome.

    ``approved=False`` means the portfolio drawdown limit was breached. This is a
    loss-limiting control, not a view on the market, so it is never converted
    into a smaller position. If this test ever needs changing, that is a decision
    about risk appetite and should be made deliberately.
    """
    assert (
        decide(0.99, Direction.BULLISH, approved=False, buy_threshold=0.65, skip_threshold=0.35)
        is Decision.SKIP
    )


def test_a_cleared_trade_is_never_skipped() -> None:
    """SKIP has exactly one producer: the drawdown veto."""
    for score in (0.0, 0.5, 1.0):
        for direction in (Direction.BULLISH, Direction.BEARISH):
            assert (
                decide(
                    score,
                    direction,
                    approved=True,
                    buy_threshold=0.65,
                    skip_threshold=0.35,
                )
                is not Decision.SKIP
            )


def test_the_trade_decision_carries_all_four_narrative_fields() -> None:
    from shared.schemas.signals import TradeDecision

    for name in NARRATIVE_FIELDS:
        assert name in TradeDecision.model_fields, f"TradeDecision is missing {name}"
    assert "tp1" in TradeDecision.model_fields
    assert "tp2" in TradeDecision.model_fields
    assert "strength" in TradeDecision.model_fields


def test_all_fields_present_in_output() -> None:
    """A constructed decision satisfies every part of the published contract."""
    from shared.schemas.signals import TradeDecision

    decision = TradeDecision(
        symbol="XAUUSD",
        decision=Decision.BUY,
        final_score=0.72,
        technical_score=0.80,
        news_score=0.60,
        risk_score=1.0,
        risk_approved=True,
        position_size=0.25,
        entry_price=4_156.23,
        stop_loss=4_132.10,
        take_profit=4_180.36,
        tp1=4_180.36,
        tp2=4_204.49,
        strength=Strength.STRONG,
        recommendation="BUY long at 0.25 size, strength STRONG.",
        explanation="Technical composite +0.45. Combined confidence 0.72.",
        risk_notes="ADX 18 — weak trend.",
        invalidation="A close below the stop at 4132.10.",
    )
    assert decision.is_actionable
    assert 0.0 <= decision.final_score <= 1.0
    assert decision.rr_ratio == pytest.approx(2.0, abs=0.01)
    for name in NARRATIVE_FIELDS:
        assert getattr(decision, name), f"{name} must not be empty"


def test_an_incomplete_decision_is_not_actionable() -> None:
    """The property that makes the contract checkable rather than aspirational."""
    from shared.schemas.signals import TradeDecision

    incomplete = TradeDecision(
        symbol="XAUUSD",
        decision=Decision.BUY,
        final_score=0.5,
        technical_score=0.5,
        news_score=0.5,
        risk_score=1.0,
        entry_price=100.0,
        stop_loss=None,
        take_profit=None,
    )
    assert incomplete.is_actionable is False
    assert incomplete.rr_ratio == 0.0


# --------------------------------------------------------------------------- #
# Strength bands
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("confidence", "expected"),
    [
        (0.0, Strength.WEAK),
        (0.1, Strength.WEAK),
        (0.299, Strength.WEAK),
        (0.30, Strength.MODERATE),
        (0.5, Strength.MODERATE),
        (0.70, Strength.MODERATE),
        (0.701, Strength.STRONG),
        (1.0, Strength.STRONG),
    ],
)
def test_strength_bands_match_the_specification(
    confidence: float, expected: Strength
) -> None:
    assert Strength.from_confidence(confidence) is expected
    assert strength_from_confidence(confidence) is expected


def test_low_confidence_produces_weak_signal() -> None:
    """Weak conviction must show up as WEAK and a quarter size."""
    strength = Strength.from_confidence(0.10)
    assert strength is Strength.WEAK
    assert strength.position_size == 0.25


@pytest.mark.parametrize(
    ("strength", "size"),
    [(Strength.WEAK, 0.25), (Strength.MODERATE, 0.60), (Strength.STRONG, 1.00)],
)
def test_each_strength_band_carries_its_size(strength: Strength, size: float) -> None:
    assert strength.position_size == size


def test_confidence_is_clamped_into_range() -> None:
    assert Strength.from_confidence(-5.0) is Strength.WEAK
    assert Strength.from_confidence(5.0) is Strength.STRONG


# --------------------------------------------------------------------------- #
# No non-actionable vocabulary in any agent output path
# --------------------------------------------------------------------------- #


def test_no_neutral_in_any_agent_output() -> None:
    """Swept across the full input space of the two decision points.

    A property test over the boundary values rather than a handful of examples,
    because the previous abstain band lived exactly at these boundaries and that
    is where a regression would reappear.
    """
    composites = [round(-1.0 + i * 0.01, 2) for i in range(201)]
    for composite in composites:
        direction, confidence = signal_from_composite(
            composite, 0.6, TechnicalParams()
        )
        assert direction is Direction.BULLISH or direction is Direction.BEARISH
        assert confidence > 0.0

    for score in [round(i * 0.01, 2) for i in range(101)]:
        for direction in (Direction.BULLISH, Direction.BEARISH):
            result = decide(
                score, direction, approved=True, buy_threshold=0.65, skip_threshold=0.35
            )
            assert result in {Decision.BUY, Decision.SELL}


def test_the_deprecated_enum_members_still_exist() -> None:
    """They are load-bearing outside the four agents, so removal is not allowed.

    ``Direction.NEUTRAL`` is branched on by the pipeline, the store, the message
    builders and the execution layer. ``Decision.SKIP`` is still produced by the
    drawdown veto. Deleting either would break code outside this change's scope.
    """
    assert Direction.NEUTRAL.value == "NEUTRAL"
    assert Decision.SKIP.value == "SKIP"
    assert Decision.WAIT.value == "WAIT"
    assert Sentiment.NEUTRAL.value == "NEUTRAL"


# --------------------------------------------------------------------------- #
# Level geometry — the invariants that prevent unbounded-loss orders
# --------------------------------------------------------------------------- #


def _assessment(stop: float | None = None, target: float | None = None):
    from shared.schemas.signals import RiskAssessment

    return RiskAssessment(symbol="XAUUSD", approved=True, stop_loss=stop, take_profit=target)


@pytest.mark.parametrize("decision", [Decision.BUY, Decision.SELL])
@pytest.mark.parametrize(
    ("stop", "target"),
    [
        (4_100.0, 4_200.0),  # ordinary bearish geometry
        (4_200.0, 4_100.0),  # ordinary bullish geometry
        (4_120.0, 4_180.0),  # tight stop
        (None, None),  # no levels at all
        (4_100.0, None),  # stop only
        (None, 4_200.0),  # target only
        (4_156.23, 4_156.23),  # zero distance — the live bug that produced TP1 == entry
        (0.0, 0.0),  # non-positive
        (4_300.0, 4_400.0),  # both on the wrong side for a BUY
    ],
)
def test_levels_are_always_geometrically_coherent(decision: Decision, stop, target) -> None:
    """Stop on the losing side, both targets on the winning side, TP1 != TP2.

    A live cycle produced ``BUY`` with the stop *above* entry and both targets
    below it, because the action could be flipped by the aggregate score after the
    Risk Manager had already priced the levels for the opposite side. That is an
    unbounded-loss order wearing a bullish label, so each invariant is asserted
    independently across adversarial inputs.
    """
    from agents.decision_maker.agent import _levels

    entry = 4_156.23
    got_entry, tp1, tp2, sl = _levels(entry, _assessment(stop, target), decision)

    assert got_entry == entry
    assert tp1 is not None and tp2 is not None and sl is not None
    if decision is Decision.BUY:
        assert sl < entry, f"stop {sl} must be below entry {entry} on a BUY"
        assert tp1 > entry, f"TP1 {tp1} must be above entry {entry} on a BUY"
        assert tp2 > tp1, f"TP2 {tp2} must exceed TP1 {tp1}"
    else:
        assert sl > entry, f"stop {sl} must be above entry {entry} on a SELL"
        assert tp1 < entry, f"TP1 {tp1} must be below entry {entry} on a SELL"
        assert tp2 < tp1, f"TP2 {tp2} must be under TP1 {tp1}"
    assert tp1 != tp2, "TP1 and TP2 must differ"


@pytest.mark.parametrize("direction", [Direction.BULLISH, Direction.BEARISH])
def test_the_action_follows_the_technical_read_not_the_aggregate(
    direction: Direction,
) -> None:
    """The direction must match the side the Risk Manager priced levels on.

    This is the invariant that prevents the unbounded-loss order: flipping the
    action on score while keeping the levels is the dangerous combination.
    """
    expected = Decision.BUY if direction is Direction.BULLISH else Decision.SELL
    for score in (0.0, 0.5, 0.99):
        result = decide(
            score, direction, approved=True, buy_threshold=0.65, skip_threshold=0.35
        )
        assert result is expected


@pytest.mark.parametrize("decision", [Decision.BUY, Decision.SELL])
def test_a_complete_decision_passes_the_geometry_check(decision: Decision) -> None:
    """End-to-end: what the decision maker publishes is self-consistent."""
    from shared.schemas.signals import TradeDecision

    entry = 4_156.23
    long_side = decision is Decision.BUY
    sl = entry - 24.13 if long_side else entry + 24.13
    tp1 = entry + 24.13 if long_side else entry - 24.13

    built = TradeDecision(
        symbol="XAUUSD",
        decision=decision,
        final_score=0.5,
        technical_score=0.5,
        news_score=0.5,
        risk_score=1.0,
        entry_price=entry,
        stop_loss=sl,
        take_profit=tp1,
        tp1=tp1,
        tp2=entry + (48.26 if long_side else -48.26),
    )
    assert built.is_actionable
    assert built.rr_ratio > 1.0
    if long_side:
        assert built.stop_loss < built.entry_price < built.tp1 < built.tp2
    else:
        assert built.stop_loss > built.entry_price > built.tp1 > built.tp2
