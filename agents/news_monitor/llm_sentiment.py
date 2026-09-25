"""Sentiment classification for news headlines and event text.

The default is a transparent, deterministic lexicon classifier that needs no
API key. When an OpenAI-compatible LLM is configured, the LLM classifier is
used with the lexicon as an automatic fallback on any error.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from shared.config import Settings
from shared.llm import LLMClient, build_llm_client
from shared.logging import get_logger
from shared.schemas.enums import Sentiment

_logger = get_logger(__name__)

_BULLISH_TERMS: dict[str, float] = {
    "surge": 1.0,
    "surges": 1.0,
    "rally": 1.0,
    "rallies": 1.0,
    "soar": 1.0,
    "soars": 1.0,
    "gain": 0.6,
    "gains": 0.6,
    "rise": 0.5,
    "rises": 0.5,
    "climb": 0.6,
    "climbs": 0.6,
    "record high": 1.0,
    "bullish": 1.0,
    "upbeat": 0.7,
    "dovish": 0.8,
    "rate cut": 1.0,
    "stimulus": 0.8,
    "weak dollar": 0.9,
    "inflows": 0.7,
    "etf approval": 1.0,
    "adoption": 0.7,
    "safe haven": 0.6,
    "recovery": 0.6,
}

_BEARISH_TERMS: dict[str, float] = {
    "plunge": 1.0,
    "plunges": 1.0,
    "crash": 1.0,
    "slump": 0.9,
    "slumps": 0.9,
    "fall": 0.5,
    "falls": 0.5,
    "drop": 0.5,
    "drops": 0.5,
    "decline": 0.5,
    "declines": 0.5,
    "selloff": 0.9,
    "sell-off": 0.9,
    "bearish": 1.0,
    "hawkish": 0.8,
    "rate hike": 1.0,
    "tightening": 0.8,
    "strong dollar": 0.9,
    "recession": 0.9,
    "outflows": 0.7,
    "crackdown": 0.8,
    "ban": 0.9,
    "liquidation": 0.8,
    "risk-off": 0.7,
}

_SYSTEM = "You are a financial sentiment classifier. Reply with strict JSON only, no prose."
_PROMPT = (
    "Classify the overall market sentiment of these financial headlines for gold "
    "and bitcoin. Reply with strict JSON: "
    '{{"sentiment": one of VERY_BULLISH|BULLISH|NEUTRAL|BEARISH|VERY_BEARISH, '
    '"confidence": number between 0 and 1, "rationale": short string}}.\n\n{headlines}'
)


@dataclass(frozen=True)
class SentimentResult:
    """The outcome of classifying one or more texts."""

    sentiment: Sentiment
    confidence: float
    rationale: str


@runtime_checkable
class SentimentClassifier(Protocol):
    """Classify a batch of texts into a single aggregate sentiment."""

    async def classify(self, texts: list[str]) -> SentimentResult:
        """Return the aggregate sentiment for ``texts``."""


class LexiconSentimentClassifier:
    """Deterministic keyword-based sentiment classifier.

    Scores each text by the weighted count of bullish minus bearish terms,
    normalised by the total number of matches.
    """

    def __init__(
        self,
        bullish: dict[str, float] | None = None,
        bearish: dict[str, float] | None = None,
    ) -> None:
        self._bullish = bullish or _BULLISH_TERMS
        self._bearish = bearish or _BEARISH_TERMS

    async def classify(self, texts: list[str]) -> SentimentResult:
        """Classify ``texts`` using the lexicon."""
        if not texts:
            return SentimentResult(Sentiment.NEUTRAL, 0.5, "No text to classify")

        bull_score = 0.0
        bear_score = 0.0
        matches: list[str] = []
        for text in texts:
            lowered = text.lower()
            for term, weight in self._bullish.items():
                if term in lowered:
                    bull_score += weight
                    matches.append(f"+{term}")
            for term, weight in self._bearish.items():
                if term in lowered:
                    bear_score += weight
                    matches.append(f"-{term}")

        total = bull_score + bear_score
        if total == 0.0:
            return SentimentResult(Sentiment.NEUTRAL, 0.4, "No sentiment terms detected")

        normalised = (bull_score - bear_score) / total
        sentiment = _bucket(normalised)
        confidence = round(min(0.95, 0.45 + 0.5 * min(total / 5.0, 1.0)), 4)
        rationale = f"lexicon score {normalised:+.2f} from {len(matches)} term(s)"
        return SentimentResult(sentiment, confidence, rationale)


class LLMSentimentClassifier:
    """LLM-backed sentiment classifier with a lexicon fallback.

    Args:
        client: An OpenAI-compatible client.
        fallback: Classifier used when the LLM call fails.
    """

    def __init__(self, client: LLMClient, *, fallback: SentimentClassifier | None = None) -> None:
        self._client = client
        self._fallback = fallback or LexiconSentimentClassifier()

    async def classify(self, texts: list[str]) -> SentimentResult:
        """Classify ``texts`` with the LLM, falling back on any error."""
        if not texts:
            return SentimentResult(Sentiment.NEUTRAL, 0.5, "No text to classify")
        try:
            headlines = "\n".join(f"- {text}" for text in texts[:20])
            payload = await self._client.complete_json(
                _PROMPT.format(headlines=headlines), system=_SYSTEM
            )
            return SentimentResult(
                sentiment=Sentiment(payload["sentiment"]),
                confidence=float(payload.get("confidence", 0.5)),
                rationale=str(payload.get("rationale", "llm")),
            )
        except Exception as exc:
            _logger.warning("sentiment.llm_failed", error=repr(exc))
            return await self._fallback.classify(texts)


def build_sentiment_classifier(settings: Settings) -> SentimentClassifier:
    """Return the configured classifier, or the lexicon default."""
    lexicon = LexiconSentimentClassifier()
    client = build_llm_client(settings)
    if client is not None:
        return LLMSentimentClassifier(client, fallback=lexicon)
    return lexicon


def _bucket(score: float) -> Sentiment:
    if score >= 0.5:
        return Sentiment.VERY_BULLISH
    if score >= 0.15:
        return Sentiment.BULLISH
    if score <= -0.5:
        return Sentiment.VERY_BEARISH
    if score <= -0.15:
        return Sentiment.BEARISH
    return Sentiment.NEUTRAL
