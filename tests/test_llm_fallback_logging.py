"""Tests that a degraded LLM call is visible rather than silent.

Every narrator, classifier and reasoner falls back to a deterministic template
when the model fails. The fallback produces output indistinguishable from a real
response — a plausible signal with a round confidence — so the only evidence a
cycle was degraded is the log line. These tests pin that the line exists, is at
WARNING, and carries the machine-readable reason.
"""

from __future__ import annotations

from typing import Any

import pytest

from agents.decision_maker.llm_reasoner import LLMReasoner
from agents.news_monitor.llm_sentiment import LLMSentimentClassifier
from agents.risk_manager.narrator import LLMRiskNarrator
from agents.technical_analyst.narrator import LLMSignalNarrator
from shared.llm import REASON_BUDGET, REASON_RATE_LIMITED, LLMClient, LLMError

_EVENTS: list[tuple[str, dict[str, Any]]] = []


@pytest.fixture(autouse=True)
def _capture_logs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Intercept structlog WARNING events from the four fallback modules."""
    _EVENTS.clear()

    def _capture(event: str, *args: Any, **kwargs: Any) -> None:
        if isinstance(event, str) and event.endswith("_failed"):
            _EVENTS.append((event, kwargs))

    for module in (
        "agents.technical_analyst.narrator",
        "agents.risk_manager.narrator",
        "agents.news_monitor.llm_sentiment",
        "agents.decision_maker.llm_reasoner",
    ):
        mod = __import__(module, fromlist=["_logger"])
        monkeypatch.setattr(mod._logger, "warning", _capture)
    yield
    _EVENTS.clear()


def _dead_client() -> LLMClient:
    """A client whose every call fails with a classified LLMError."""
    client = LLMClient(base_url="https://x.test/v1", api_key="k", model="m")

    async def _boom(*_a: Any, **_k: Any) -> str:
        raise LLMError(
            "budget gone", reason=REASON_BUDGET, attempts=2, status=429
        )

    object.__setattr__(client, "_test_boom", _boom)
    return client


class _AlwaysFails(LLMClient):
    """Client that raises a classified LLMError on every call."""

    def __init__(self) -> None:
        super().__init__(base_url="https://x.test/v1", api_key="k", model="m")

    async def complete(self, prompt: str, *, system: str | None = None) -> str:
        raise LLMError("budget gone", reason=REASON_BUDGET, attempts=2, status=429)

    async def complete_json(
        self, prompt: str, *, system: str | None = None
    ) -> dict[str, Any]:
        raise LLMError("budget gone", reason=REASON_BUDGET, attempts=2, status=429)


CONTEXT = {"symbol": "XAUUSD", "timeframe": "H1", "reasoning": "template text"}


async def test_technical_narrator_logs_reason_and_attempts() -> None:
    narrator = LLMSignalNarrator(_AlwaysFails())
    out = await narrator.narrate(dict(CONTEXT))
    assert out == "template text"

    name, kwargs = _EVENTS[-1]
    assert name == "narrator.technical_failed"
    assert kwargs["reason"] == REASON_BUDGET
    assert kwargs["attempts"] == 2
    assert kwargs["symbol"] == "XAUUSD"
    assert kwargs["timeframe"] == "H1"


async def test_technical_narrator_logs_correlation_id_when_present() -> None:
    """The id is threaded in from analyze() and lets a drop be attributed."""
    narrator = LLMSignalNarrator(_AlwaysFails())
    context = {**CONTEXT, "correlation_id": "cycle-abc123"}
    await narrator.narrate(context)
    assert _EVENTS[-1][1]["correlation_id"] == "cycle-abc123"


async def test_technical_narrator_tolerates_a_missing_correlation_id() -> None:
    narrator = LLMSignalNarrator(_AlwaysFails())
    await narrator.narrate(dict(CONTEXT))
    assert _EVENTS[-1][1]["correlation_id"] is None


async def test_risk_narrator_logs_reason_and_attempts() -> None:
    narrator = LLMRiskNarrator(_AlwaysFails())
    out = await narrator.narrate(dict(CONTEXT))
    assert out == "template text"

    name, kwargs = _EVENTS[-1]
    assert name == "narrator.risk_failed"
    assert kwargs["reason"] == REASON_BUDGET
    assert kwargs["attempts"] == 2
    assert kwargs["symbol"] == "XAUUSD"


async def test_sentiment_classifier_logs_reason_and_attempts() -> None:
    classifier = LLMSentimentClassifier(_AlwaysFails())
    result = await classifier.classify(["Gold rallies on dovish Fed"])
    assert result.sentiment.value  # fell back to the lexicon

    name, kwargs = _EVENTS[-1]
    assert name == "sentiment.llm_failed"
    assert kwargs["reason"] == REASON_BUDGET
    assert kwargs["attempts"] == 2
    assert kwargs["headline_count"] == 1


async def test_reasoner_explain_logs_reason_and_attempts() -> None:
    reasoner = LLMReasoner(_AlwaysFails())
    out = await reasoner.explain(dict(CONTEXT))
    assert out

    name, kwargs = _EVENTS[-1]
    assert name == "reasoner.llm_failed"
    assert kwargs["reason"] == REASON_BUDGET
    assert kwargs["attempts"] == 2


async def test_reasoner_review_logs_reason_and_attempts() -> None:
    """A review fallback means the adjustment defaulted to zero, which is
    otherwise indistinguishable from a legitimate 'no adjustment'."""
    reasoner = LLMReasoner(_AlwaysFails())
    review = await reasoner.review(dict(CONTEXT))
    assert review.confidence_adjustment == 0.0

    name, kwargs = _EVENTS[-1]
    assert name == "reasoner.review_failed"
    assert kwargs["reason"] == REASON_BUDGET
    assert kwargs["attempts"] == 2


async def test_rate_limited_is_distinguishable_from_budget() -> None:
    """The two causes need different responses, so the log must tell them apart."""

    class _RateLimited(_AlwaysFails):
        async def complete(self, prompt: str, *, system: str | None = None) -> str:
            raise LLMError("HTTP 429", reason=REASON_RATE_LIMITED, attempts=3, status=429)

    narrator = LLMSignalNarrator(_RateLimited())
    await narrator.narrate(dict(CONTEXT))
    assert _EVENTS[-1][1]["reason"] == REASON_RATE_LIMITED
    assert _EVENTS[-1][1]["attempts"] == 3


async def test_unclassified_exception_still_logs() -> None:
    """A non-LLMError must not break the log line's shape."""

    class _Weird(_AlwaysFails):
        async def complete(self, prompt: str, *, system: str | None = None) -> str:
            raise RuntimeError("something else entirely")

    narrator = LLMSignalNarrator(_Weird())
    await narrator.narrate(dict(CONTEXT))
    assert _EVENTS[-1][1]["reason"] == "unknown"
    assert _EVENTS[-1][1]["attempts"] == 1
