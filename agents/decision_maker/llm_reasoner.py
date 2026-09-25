"""Optional LLM narrative generation and chain-of-thought review.

The system always has a deterministic template reasoner; an LLM reasoner is
used when an OpenAI-compatible provider is configured and falls back to the
template on any error.

Beyond the narrative :meth:`~DecisionReasoner.explain`, the reasoner can review
a decision and return structured fields — ``consistent``, ``conflicts``,
``red_flags`` and a bounded ``confidence_adjustment`` (backend-v2, Problem 10).
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from shared.config import Settings
from shared.llm import LLMClient, build_llm_client
from shared.logging import get_logger

_logger = get_logger(__name__)

_SYSTEM = "You explain algorithmic trading decisions concisely and factually."
_PROMPT = (
    "Explain this algorithmic trading decision in at most three sentences. Be "
    "specific about which signals drove it and what would invalidate it.\n"
    "Context: {context}"
)

_REVIEW_SYSTEM = (
    "You are a rigorous risk reviewer for an algorithmic trading system. "
    "Return only a valid JSON object, no prose."
)
_REVIEW_PROMPT = (
    "Review the trade-decision context below. Reason step by step, then return "
    "a JSON object with exactly these fields: "
    '{{"consistent": <bool>, "conflicts": [<strings>], "red_flags": [<strings>], '
    '"confidence_adjustment": <float in [-{max_adjustment:.2f}, {max_adjustment:.2f}]>}}. '
    "Only flag real issues; be conservative and factual.\n"
    "Context: {context}"
)


class DecisionReview(BaseModel):
    """Structured review of a trade decision (Problem 10)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    consistent: bool = True
    conflicts: tuple[str, ...] = ()
    red_flags: tuple[str, ...] = ()
    confidence_adjustment: float = Field(default=0.0, ge=-1.0, le=1.0)


@runtime_checkable
class DecisionReasoner(Protocol):
    """Produce a rationale and a structured review for a trade decision."""

    async def explain(self, context: dict[str, Any]) -> str:
        """Return a rationale for the decision described by ``context``."""

    async def review(self, context: dict[str, Any]) -> DecisionReview:
        """Return a structured review of the decision described by ``context``."""


class TemplateReasoner:
    """Deterministic, dependency-free rationale generator."""

    def __init__(self, *, max_adjustment: float = 0.10) -> None:
        self._max_adjustment = max_adjustment

    async def explain(self, context: dict[str, Any]) -> str:
        """Render a concise rationale from the decision context."""
        symbol = context.get("symbol", "?")
        decision = context.get("decision", "?")
        final = float(context.get("final_score") or 0.0)
        technical = context.get("technical_direction", "?")
        news = context.get("news_sentiment", "?")
        risk = context.get("risk_reasoning", "")
        return (
            f"{decision} {symbol}: weighted score "
            f"{final:.2f} (technical {technical}, news {news}). {risk}"
        ).strip()

    async def review(self, context: dict[str, Any]) -> DecisionReview:
        """Deterministic review: surface the cross-check warnings as conflicts."""
        warnings = tuple(str(item) for item in (context.get("warnings") or []))
        return DecisionReview(consistent=not warnings, conflicts=warnings)


class LLMReasoner:
    """LLM-backed reasoner with a template fallback.

    Args:
        client: An OpenAI-compatible client.
        fallback: Reasoner used when the LLM call fails.
        max_adjustment: Upper bound for the LLM confidence adjustment.
    """

    def __init__(
        self,
        client: LLMClient,
        *,
        fallback: DecisionReasoner | None = None,
        max_adjustment: float = 0.10,
    ) -> None:
        self._client = client
        self._fallback = fallback or TemplateReasoner(max_adjustment=max_adjustment)
        self._max_adjustment = max_adjustment

    async def explain(self, context: dict[str, Any]) -> str:
        """Return an LLM rationale, falling back to the template on error."""
        try:
            return await self._client.complete(_PROMPT.format(context=context), system=_SYSTEM)
        except Exception as exc:
            _logger.warning("reasoner.llm_failed", error=repr(exc))
            return await self._fallback.explain(context)

    async def review(self, context: dict[str, Any]) -> DecisionReview:
        """Return a structured LLM review, falling back to the template."""
        try:
            prompt = _REVIEW_PROMPT.format(
                context=context, max_adjustment=self._max_adjustment
            )
            raw = await self._client.complete_json(prompt, system=_REVIEW_SYSTEM)
            review = DecisionReview.model_validate(raw)
            adjustment = max(
                -self._max_adjustment, min(self._max_adjustment, review.confidence_adjustment)
            )
            return DecisionReview(
                consistent=review.consistent,
                conflicts=review.conflicts,
                red_flags=review.red_flags,
                confidence_adjustment=adjustment,
            )
        except Exception as exc:
            _logger.warning("reasoner.review_failed", error=repr(exc))
            return await self._fallback.review(context)


def build_reasoner(settings: Settings) -> DecisionReasoner:
    """Return the configured reasoner, or the template default."""
    template = TemplateReasoner(max_adjustment=settings.llm_review_adjustment_max)
    client = build_llm_client(settings)
    if client is not None:
        return LLMReasoner(
            client,
            fallback=template,
            max_adjustment=settings.llm_review_adjustment_max,
        )
    return template
