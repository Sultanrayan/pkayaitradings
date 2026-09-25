"""Optional LLM narration for risk assessments.

Keeps the deterministic checks intact: the narrator only turns the result into
readable reasoning, and falls back to the rule-based text.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from shared.config import Settings
from shared.llm import LLMClient, build_llm_client
from shared.logging import get_logger

_logger = get_logger(__name__)

_SYSTEM = "You explain pre-trade risk assessments concisely and factually."
_PROMPT = (
    "Explain this risk assessment in at most three sentences. State whether the "
    "trade is approved or vetoed and the main reasons.\nContext: {context}"
)


@runtime_checkable
class RiskNarrator(Protocol):
    """Turn a risk assessment into readable reasoning."""

    async def narrate(self, context: dict[str, Any]) -> str:
        """Return reasoning text for the assessment described by ``context``."""


class TemplateRiskNarrator:
    """Returns the rule-based reasoning unchanged."""

    async def narrate(self, context: dict[str, Any]) -> str:
        """Return the deterministic reasoning from ``context``."""
        return str(context.get("reasoning", "")).strip()


class LLMRiskNarrator:
    """LLM-backed narrator with a template fallback."""

    def __init__(self, client: LLMClient, *, fallback: RiskNarrator | None = None) -> None:
        self._client = client
        self._fallback = fallback or TemplateRiskNarrator()

    async def narrate(self, context: dict[str, Any]) -> str:
        """Return an LLM narrative, falling back to the template on error."""
        try:
            return await self._client.complete(_PROMPT.format(context=context), system=_SYSTEM)
        except Exception as exc:
            _logger.warning("narrator.risk_failed", error=repr(exc))
            return await self._fallback.narrate(context)


def build_risk_narrator(settings: Settings) -> RiskNarrator:
    """Return the configured narrator, or the template default."""
    template = TemplateRiskNarrator()
    client = build_llm_client(settings)
    if client is not None:
        return LLMRiskNarrator(client, fallback=template)
    return template
