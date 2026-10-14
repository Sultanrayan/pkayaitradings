"""Optional LLM narration for technical signals.

Keeps the deterministic strategy intact: the narrator only turns the computed
signal into readable reasoning, and falls back to the rule-based text.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from shared.config import Settings
from shared.llm import LLMClient, build_analysis_llm_client
from shared.logging import get_logger

_logger = get_logger(__name__)

_SYSTEM = "You explain technical analysis signals concisely and factually."
_PROMPT = (
    "Explain this technical signal in at most three sentences. Mention the main "
    "drivers and what would invalidate it.\n"
    "You MUST always describe a direction. Never output SKIP, WAIT, NEUTRAL, or "
    "'no trade'. If the indicators are mixed, name the direction the evidence "
    "leans toward and state the weakness explicitly as a low-confidence call.\n"
    "Context: {context}"
)


@runtime_checkable
class SignalNarrator(Protocol):
    """Turn a technical signal into readable reasoning."""

    async def narrate(self, context: dict[str, Any]) -> str:
        """Return reasoning text for the signal described by ``context``."""


class TemplateSignalNarrator:
    """Returns the rule-based reasoning unchanged."""

    async def narrate(self, context: dict[str, Any]) -> str:
        """Return the deterministic reasoning from ``context``."""
        return str(context.get("reasoning", "")).strip()


class LLMSignalNarrator:
    """LLM-backed narrator with a template fallback."""

    def __init__(self, client: LLMClient, *, fallback: SignalNarrator | None = None) -> None:
        self._client = client
        self._fallback = fallback or TemplateSignalNarrator()

    async def narrate(self, context: dict[str, Any]) -> str:
        """Return an LLM narrative, falling back to the template on error."""
        try:
            return await self._client.complete(_PROMPT.format(context=context), system=_SYSTEM)
        except Exception as exc:
            # The fallback is indistinguishable from a real reading unless it is
            # logged: a template narrative produces a perfectly plausible signal
            # with a round confidence. reason/attempts say whether the model was
            # rate limited, timed out, or ran out of budget.
            _logger.warning(
                "narrator.technical_failed",
                error=repr(exc),
                reason=getattr(exc, "reason", "unknown"),
                attempts=getattr(exc, "attempts", 1),
                symbol=context.get("symbol"),
                timeframe=context.get("timeframe"),
                correlation_id=context.get("correlation_id"),
            )
            return await self._fallback.narrate(context)


def build_signal_narrator(settings: Settings) -> SignalNarrator:
    """Return the configured narrator, or the template default."""
    template = TemplateSignalNarrator()
    client = build_analysis_llm_client(settings)
    if client is not None:
        return LLMSignalNarrator(client, fallback=template)
    return template
