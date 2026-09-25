"""Tests for the LLM chain-of-thought review layer (Problem 10)."""

from __future__ import annotations

import pytest

from agents.decision_maker.llm_reasoner import (
    DecisionReview,
    LLMReasoner,
    TemplateReasoner,
)
from shared.config import Settings
from shared.llm import LLMError


class _StubLLMClient:
    def __init__(self, responses: list[dict[str, object]] | None = None) -> None:
        self._responses = list(responses or [])

    async def complete_json(self, prompt: str, *, system: str | None = None) -> dict[str, object]:
        if not self._responses:
            raise LLMError("no stub response")
        return self._responses.pop(0)


async def test_template_review_surfaces_warnings() -> None:
    reasoner = TemplateReasoner()
    review = await reasoner.review({"warnings": ["Technical BULLISH conflicts with news BEARISH"]})
    assert review.consistent is False
    assert "conflicts with news" in review.conflicts[0]
    assert review.confidence_adjustment == 0.0


async def test_template_review_consistent_without_warnings() -> None:
    reasoner = TemplateReasoner()
    review = await reasoner.review({"warnings": []})
    assert review.consistent is True
    assert review.conflicts == ()


async def test_llm_review_parses_and_bounds_adjustment() -> None:
    client = _StubLLMClient(
        [
            {
                "consistent": False,
                "conflicts": ["news hawkish vs technical bullish"],
                "red_flags": ["high impact event"],
                "confidence_adjustment": 0.3,  # exceeds the bound
            }
        ]
    )
    reasoner = LLMReasoner(client, max_adjustment=0.10)  # type: ignore[arg-type]
    review = await reasoner.review({})
    assert review.consistent is False
    assert review.conflicts == ("news hawkish vs technical bullish",)
    assert review.red_flags == ("high impact event",)
    assert review.confidence_adjustment == pytest.approx(0.10)


async def test_llm_review_falls_back_on_bad_json() -> None:
    client = _StubLLMClient()  # raises LLMError
    fallback = TemplateReasoner()
    reasoner = LLMReasoner(client, fallback=fallback, max_adjustment=0.10)  # type: ignore[arg-type]
    review = await reasoner.review({"warnings": ["conflict"]})
    assert review.consistent is False
    assert review.conflicts == ("conflict",)


async def test_llm_review_rejects_extra_keys() -> None:
    client = _StubLLMClient([{"consistent": True, "unexpected": "key"}])
    fallback = TemplateReasoner()
    reasoner = LLMReasoner(client, fallback=fallback)  # type: ignore[arg-type]
    review = await reasoner.review({"warnings": []})
    assert review.consistent is True  # fell back to the template
    assert review.confidence_adjustment == 0.0


def test_decision_review_validates() -> None:
    review = DecisionReview.model_validate(
        {"consistent": False, "conflicts": ["a"], "red_flags": ["b"], "confidence_adjustment": -0.05}
    )
    assert review.consistent is False
    assert review.confidence_adjustment == pytest.approx(-0.05)


def test_build_reasoner_defaults_to_template_without_llm() -> None:
    from agents.decision_maker.llm_reasoner import build_reasoner

    reasoner = build_reasoner(Settings(llm_provider="none"))
    assert isinstance(reasoner, TemplateReasoner)
