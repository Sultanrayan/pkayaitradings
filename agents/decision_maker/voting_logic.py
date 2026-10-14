"""Weighted voting logic for the Decision Maker.

Each agent contributes a ``[0, 1]`` score where ``0`` is maximally bearish and
``1`` maximally bullish:

* **Technical** — ``confidence`` for a bullish call, ``1 - confidence`` for a
  bearish call, ``0.5`` when neutral.
* **News** — the sentiment score (``0`` bearish … ``1`` bullish).
* **Risk** — ``1.0`` when the Risk Manager approves, ``0.0`` on a veto.

The final score is either the documented weighted sum (legacy)::

    Final = Technical x 0.45 + News x 0.25 + Risk x 0.30

or the non-linear weighted geometric mean recommended by the backend-v2
roadmap (Problem 5). The geometric form treats Risk as a multiplier (a veto
forces the final score to zero) and applies hard consistency rules.

:func:`decide` always returns ``BUY`` or ``SELL``. The single exception is the
Risk Manager's drawdown veto, which still returns ``SKIP``: that is a
loss-limiting control, not a view on the market.
"""

from __future__ import annotations

from dataclasses import dataclass

from shared.schemas.enums import Decision, Direction, Sentiment

_FLOOR = 1e-6
_STRONG_TECH = 0.85
_STRONG_NEWS = 0.85
_MODERATE_NEWS = 0.40
_DISAGREEMENT_CAP = 0.50


@dataclass(frozen=True)
class VoteBreakdown:
    """The individual and combined scores behind a decision."""

    technical_score: float
    news_score: float
    risk_score: float
    final_score: float


def score_technical(direction: Direction, confidence: float) -> float:
    """Map a technical signal to a bullishness score in ``[0, 1]``."""
    confidence = _clamp(confidence)
    if direction is Direction.BULLISH:
        return confidence
    if direction is Direction.BEARISH:
        return 1.0 - confidence
    return 0.5


def score_news(sentiment: Sentiment, confidence: float) -> float:
    """Map news sentiment to a bullishness score, shrunk toward neutral."""
    confidence = _clamp(confidence)
    return _clamp(0.5 + (sentiment.score - 0.5) * confidence)


def score_risk(approved: bool) -> float:
    """Map the risk verdict to a score: approved ⇒ 1.0, veto ⇒ 0.0."""
    return 1.0 if approved else 0.0


def combine(
    technical_score: float,
    news_score: float,
    risk_score: float,
    *,
    weight_technical: float,
    weight_news: float,
    weight_risk: float,
) -> VoteBreakdown:
    """Combine component scores using the configured weights."""
    total = weight_technical + weight_news + weight_risk
    if abs(total - 1.0) > 1e-6:
        raise ValueError(f"Vote weights must sum to 1.0, got {total:.4f}")
    final = technical_score * weight_technical + news_score * weight_news + risk_score * weight_risk
    return VoteBreakdown(
        technical_score=round(technical_score, 4),
        news_score=round(news_score, 4),
        risk_score=round(risk_score, 4),
        final_score=round(_clamp(final), 4),
    )


def combine_nonlinear(
    technical_score: float,
    news_score: float,
    risk_score: float,
    *,
    weight_technical: float,
    weight_news: float,
    weight_risk: float,
) -> VoteBreakdown:
    """Combine scores with a weighted geometric mean and hard consistency rules.

    ``final = technical**wt * news**wn * risk**wr`` (weights sum to 1.0), so a
    risk veto (``risk_score == 0``) collapses the score to zero. Two hard rules
    from the backend-v2 roadmap are enforced on top:

    * Tech > 0.85 and News > 0.40 — aligned strong view, left unchanged.
    * News > 0.85 but Tech < 0.40 — the score is capped at 0.50 (disagreement).
    """
    total = weight_technical + weight_news + weight_risk
    if abs(total - 1.0) > 1e-6:
        raise ValueError(f"Vote weights must sum to 1.0, got {total:.4f}")
    tech = max(_FLOOR, technical_score)
    news = max(_FLOOR, news_score)
    risk = max(0.0, risk_score)
    final = (tech**weight_technical) * (news**weight_news) * (risk**weight_risk)

    if news_score > _STRONG_NEWS and technical_score < _MODERATE_NEWS:
        final = min(final, _DISAGREEMENT_CAP)

    return VoteBreakdown(
        technical_score=round(technical_score, 4),
        news_score=round(news_score, 4),
        risk_score=round(risk_score, 4),
        final_score=round(_clamp(final), 4),
    )


def decide(
    final_score: float,
    technical_direction: Direction,
    *,
    approved: bool,
    buy_threshold: float,
    skip_threshold: float,
) -> Decision:
    """Turn a final score and direction into a concrete decision.

    Always actionable. There is no longer a middle band that returns ``WAIT`` and
    no "unclear enough" path that returns ``SKIP``: a market with no edge is the
    direction the score leans toward, with a confidence that reflects how little
    edge there is. Converting a hedge into a quarter-size position is a decision
    the caller can act on; returning nothing is not a decision at all.

    **One exception, deliberately.** ``approved=False`` still returns ``SKIP``.
    That is the Risk Manager's portfolio *drawdown* veto — a loss-limiting control
    rather than a view on the market, and the one condition where continuing to
    trade would be irresponsible rather than merely unprofitable.

    Args:
        final_score: Weighted score in ``[0, 1]``.
        technical_direction: The Technical Analyst's directional view.
        approved: Whether the Risk Manager cleared the trade. ``False`` means the
            drawdown limit was breached.
        buy_threshold: Score at or above which a long is taken.
        skip_threshold: Score at or below which a short is considered. Retained
            for scoring and display; no longer gates the outcome.

    Returns:
        ``BUY`` or ``SELL``, or ``SKIP`` on a drawdown veto.
    """
    if not approved:
        return Decision.SKIP

    # The action follows the technical read, never the aggregate.
    #
    # The Risk Manager has already priced the stop and target for
    # ``technical_direction``. Letting a high aggregate flip the action would emit
    # a BUY carrying a stop above entry and targets below it — an unbounded-loss
    # order wearing a bullish label. So the score's job is conviction (which
    # drives strength and size), not direction.
    #
    # ``NEUTRAL`` is unreachable from the agents; mapping it to BEARISH rather than
    # raising means a stale producer degrades to a wrong guess, not a crash.
    if technical_direction is Direction.BEARISH:
        return Decision.SELL
    return Decision.BUY


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
