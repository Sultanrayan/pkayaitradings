"""Tests for LLM-backed classifiers/reasoners and the ML model ensemble."""

from __future__ import annotations

from typing import Any

import pandas as pd
import pytest

from agents.decision_maker.llm_reasoner import (
    LLMReasoner,
    TemplateReasoner,
    build_reasoner,
)
from agents.news_monitor.llm_sentiment import (
    LexiconSentimentClassifier,
    LLMSentimentClassifier,
    build_sentiment_classifier,
)
from agents.technical_analyst.models.ensemble import (
    LSTMModel,
    ModelEnsemble,
    XGBoostModel,
)
from agents.technical_analyst.models.features import FEATURE_COLUMNS, build_features
from shared.config import Settings
from shared.schemas.enums import Sentiment
from tests.test_strategy import make_series


def _features() -> pd.DataFrame:
    return pd.DataFrame([[0.1] * len(FEATURE_COLUMNS)], columns=list(FEATURE_COLUMNS))


class _ReadyModel:
    def __init__(self, probability: float = 0.8, *, fail: bool = False) -> None:
        self._probability = probability
        self._fail = fail

    @property
    def is_ready(self) -> bool:
        return True

    def predict_proba(self, features: pd.DataFrame) -> float:
        if self._fail:
            raise RuntimeError("model exploded")
        return self._probability


class _NotReadyModel:
    @property
    def is_ready(self) -> bool:
        return False

    def predict_proba(self, features: pd.DataFrame) -> float:  # pragma: no cover
        raise AssertionError("should not be called")


# --- sentiment --------------------------------------------------------- #


class _FakeLLMClient:
    """Stand-in for :class:`shared.llm.LLMClient` in tests."""

    def __init__(
        self,
        *,
        json_result: dict[str, Any] | None = None,
        text: str | None = None,
        error: Exception | None = None,
    ) -> None:
        self._json = json_result
        self._text = text
        self._error = error

    async def complete(self, prompt: str, *, system: str | None = None) -> str:
        if self._error is not None:
            raise self._error
        return self._text or ""

    async def complete_json(self, prompt: str, *, system: str | None = None) -> dict[str, Any]:
        if self._error is not None:
            raise self._error
        return self._json or {}


async def test_llm_sentiment_success() -> None:
    client = _FakeLLMClient(
        json_result={"sentiment": "BULLISH", "confidence": 0.9, "rationale": "ok"}
    )
    classifier = LLMSentimentClassifier(client)  # type: ignore[arg-type]
    result = await classifier.classify(["gold up"])
    assert result.sentiment is Sentiment.BULLISH
    assert result.confidence == 0.9


async def test_llm_sentiment_falls_back_on_error() -> None:
    client = _FakeLLMClient(error=RuntimeError("api down"))
    classifier = LLMSentimentClassifier(client)  # type: ignore[arg-type]
    result = await classifier.classify(["gold rallies"])
    assert result.sentiment in {Sentiment.BULLISH, Sentiment.VERY_BULLISH}


async def test_llm_sentiment_empty() -> None:
    classifier = LLMSentimentClassifier(_FakeLLMClient())  # type: ignore[arg-type]
    result = await classifier.classify([])
    assert result.sentiment is Sentiment.NEUTRAL


def test_build_sentiment_classifier_branches() -> None:
    assert isinstance(
        build_sentiment_classifier(Settings(llm_provider="none")), LexiconSentimentClassifier
    )
    openai = build_sentiment_classifier(Settings(llm_provider="openai", llm_api_key="sk-x"))
    assert isinstance(openai, LLMSentimentClassifier)
    # provider set but no key -> lexicon
    assert isinstance(
        build_sentiment_classifier(Settings(llm_provider="openai", llm_api_key=None)),
        LexiconSentimentClassifier,
    )
    # anthropic is not supported by the shared OpenAI-compatible client -> lexicon
    assert isinstance(
        build_sentiment_classifier(Settings(llm_provider="anthropic", anthropic_api_key="sk-a")),
        LexiconSentimentClassifier,
    )


# --- reasoner ---------------------------------------------------------- #


async def test_template_reasoner() -> None:
    text = await TemplateReasoner().explain(
        {
            "symbol": "XAUUSD",
            "decision": "BUY",
            "final_score": 0.8,
            "technical_direction": "BULLISH",
            "news_sentiment": "NEUTRAL",
            "risk_reasoning": "all good",
        }
    )
    assert "BUY XAUUSD" in text


async def test_llm_reasoner_success() -> None:
    reasoner = LLMReasoner(_FakeLLMClient(text="because reasons"))  # type: ignore[arg-type]
    assert await reasoner.explain({"symbol": "XAUUSD"}) == "because reasons"


async def test_llm_reasoner_falls_back() -> None:
    reasoner = LLMReasoner(_FakeLLMClient(error=RuntimeError("nope")))  # type: ignore[arg-type]
    text = await reasoner.explain(
        {
            "symbol": "XAUUSD",
            "decision": "WAIT",
            "final_score": 0.5,
            "technical_direction": "NEUTRAL",
            "news_sentiment": "NEUTRAL",
        }
    )
    assert "WAIT" in text


def test_build_reasoner_branches() -> None:
    assert isinstance(build_reasoner(Settings(llm_provider="none")), TemplateReasoner)
    assert isinstance(
        build_reasoner(Settings(llm_provider="openai", llm_api_key="sk")), LLMReasoner
    )
    assert isinstance(
        build_reasoner(Settings(llm_provider="anthropic", anthropic_api_key="sk")),
        TemplateReasoner,
    )


# --- ensemble ---------------------------------------------------------- #


def test_model_ensemble_averages_ready_models() -> None:
    ensemble = ModelEnsemble([_ReadyModel(0.6), _ReadyModel(0.8), _NotReadyModel()])
    assert ensemble.available is True
    assert ensemble.predict(_features()) == pytest.approx(0.7)


def test_model_ensemble_without_models() -> None:
    ensemble = ModelEnsemble()
    assert ensemble.available is False
    assert ensemble.predict(_features()) is None


def test_model_ensemble_empty_features() -> None:
    ensemble = ModelEnsemble([_ReadyModel()])
    assert ensemble.predict(pd.DataFrame()) is None


def test_model_ensemble_skips_failing_models() -> None:
    ensemble = ModelEnsemble([_ReadyModel(fail=True)])
    assert ensemble.predict(_features()) is None


def test_unready_models_report_false() -> None:
    assert XGBoostModel("does-not-exist.json").is_ready is False
    assert LSTMModel("does-not-exist.pt").is_ready is False
    with pytest.raises(RuntimeError):
        XGBoostModel("does-not-exist.json").predict_proba(_features())
    with pytest.raises(RuntimeError):
        LSTMModel("does-not-exist.pt").predict_proba(_features())


def test_build_features_and_labels() -> None:
    frame = _ohlc_frame()
    features = build_features(frame)
    assert set(FEATURE_COLUMNS).issubset(features.columns)
    assert not features.empty


def test_build_features_requires_columns() -> None:
    with pytest.raises(ValueError, match="missing columns"):
        build_features(pd.DataFrame({"close": [1.0, 2.0]}))


def _ohlc_frame() -> pd.DataFrame:
    from agents.technical_analyst.strategy import to_frame

    return to_frame(make_series(300, drift=0.5))
