"""Language-model providers used by the GraphRAG engine."""

from __future__ import annotations

import json
import re
from typing import Any, Protocol


class LLMProvider(Protocol):
    def generate(self, prompt: str) -> str: ...


class OpenAIProvider:
    """OpenAI-compatible chat client over httpx (no SDK required).

    Talks to ``base_url`` (any OpenAI-compatible gateway, e.g. a proxy) so the
    engine shares the same LLM endpoint as the backend agents.
    """

    def __init__(
        self,
        api_key: str,
        model: str,
        temperature: float = 0.0,
        max_tokens: int = 2000,
        *,
        base_url: str | None = None,
    ) -> None:
        import httpx

        self._client = httpx.Client(
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        )
        self._base_url = (base_url or "https://api.openai.com/v1").rstrip("/")
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens

    def generate(self, prompt: str) -> str:
        response = self._client.post(
            f"{self._base_url}/chat/completions",
            json={
                "model": self._model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": self._temperature,
                "max_tokens": self._max_tokens,
            },
        )
        response.raise_for_status()
        payload = response.json()
        return payload["choices"][0]["message"].get("content") or ""


class AnthropicProvider:
    def __init__(
        self,
        api_key: str,
        model: str,
        temperature: float = 0.0,
        max_tokens: int = 2000,
    ) -> None:
        from anthropic import Anthropic

        self._client = Anthropic(api_key=api_key)
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens

    def generate(self, prompt: str) -> str:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            temperature=self._temperature,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(block.text for block in response.content if hasattr(block, "text"))


class DeterministicProvider:
    """Offline provider that exposes retrieved correction rules in demo responses."""

    def __init__(self, critic: bool = False) -> None:
        self._critic = critic

    def generate(self, prompt: str) -> str:
        if self._critic:
            return json.dumps(
                {
                    "is_correct": True,
                    "reason": "Offline critic accepted the response.",
                    "confidence": 0.5,
                }
            )
        rules = re.findall(r"Correct approach:\s*['\"]?(.+?)['\"]?(?:\n|$)", prompt)
        question = re.search(r"Question:\s*(.+?)(?:\n|$)", prompt)
        if rules:
            return f"Based on a recorded correction: {rules[0].strip()}"
        if question:
            return f"No configured LLM provider is available. Query received: {question.group(1).strip()}"
        return "No configured LLM provider is available."


def create_llm_provider(settings: Any, model: str, *, critic: bool = False) -> LLMProvider:
    provider = settings.llm_provider.lower()
    if provider in {"auto", "openai"} and settings.openai_api_key:
        try:
            return OpenAIProvider(
                settings.openai_api_key,
                model,
                temperature=0.0 if critic else settings.llm_temperature,
                max_tokens=settings.llm_max_tokens,
                base_url=settings.openai_base_url,
            )
        except Exception:
            if provider == "openai":
                raise
    if provider in {"auto", "anthropic"} and settings.anthropic_api_key:
        try:
            return AnthropicProvider(
                settings.anthropic_api_key,
                model,
                temperature=0.0 if critic else settings.llm_temperature,
                max_tokens=settings.llm_max_tokens,
            )
        except Exception:
            if provider == "anthropic":
                raise
    return DeterministicProvider(critic=critic)
