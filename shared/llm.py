"""Minimal OpenAI-compatible chat client shared by the agents.

Works with any OpenAI-compatible gateway (OpenAI, Azure-style proxies, or a
self-hosted router such as relaymodels) by pointing ``LLM_BASE_URL`` at the
``/v1`` endpoint. Uses httpx only, so no extra SDK is required.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

import httpx

from shared.config import Settings
from shared.logging import get_logger

_logger = get_logger(__name__)

_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


class LLMError(Exception):
    """Raised when the LLM endpoint fails or returns an unusable response."""


@dataclass(frozen=True)
class LLMClient:
    """A thin OpenAI-compatible chat-completions client."""

    base_url: str
    api_key: str
    model: str
    timeout: float = 30.0
    temperature: float = 0.2
    max_tokens: int = 512
    max_retries: int = 2

    async def complete(self, prompt: str, *, system: str | None = None) -> str:
        """Send a chat completion and return the assistant message text.

        Retries transient failures (timeouts, 429 and 5xx) with a short backoff.
        """
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        url = f"{self.base_url.rstrip('/')}/chat/completions"
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(url, json=payload, headers=headers)
                if response.status_code in _RETRYABLE_STATUS and attempt < self.max_retries:
                    last_error = LLMError(f"HTTP {response.status_code}")
                    await asyncio.sleep(1.5 * (attempt + 1))
                    continue
                response.raise_for_status()
                data = response.json()
                message = data["choices"][0]["message"]
                content = message.get("content")
                if not isinstance(content, str) or not content.strip():
                    # Reasoning models sometimes leave content empty and put the
                    # text in reasoning_content; use it as a fallback.
                    content = message.get("reasoning_content")
                if not isinstance(content, str) or not content.strip():
                    raise LLMError("LLM returned an empty response")
                return content.strip()
            except httpx.TransportError as exc:
                last_error = exc
                if attempt < self.max_retries:
                    await asyncio.sleep(1.5 * (attempt + 1))
                    continue
            except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
                raise LLMError(f"LLM request failed: {exc!r}") from exc

        raise LLMError(f"LLM request failed after retries: {last_error!r}")

    async def complete_json(self, prompt: str, *, system: str | None = None) -> dict[str, Any]:
        """Send a chat completion and parse a JSON object from the reply."""
        raw = await self.complete(prompt, system=system)
        return extract_json_object(raw)


def extract_json_object(text: str) -> dict[str, Any]:
    """Extract the first valid JSON object from ``text``.

    Tolerates markdown fences and surrounding prose (reasoning models often add
    both). Raises :class:`LLMError` when no object can be parsed.
    """
    cleaned = text.strip()
    if "```" in cleaned:
        for part in cleaned.split("```"):
            candidate = part.strip()
            if candidate.startswith("json"):
                candidate = candidate[4:].strip()
            if candidate.startswith("{"):
                cleaned = candidate
                break

    try:
        direct = json.loads(cleaned)
        if isinstance(direct, dict):
            return direct
    except ValueError:
        pass

    start = cleaned.find("{")
    while start != -1:
        depth = 0
        for index in range(start, len(cleaned)):
            char = cleaned[index]
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    try:
                        parsed = json.loads(cleaned[start : index + 1])
                    except ValueError:
                        break
                    if isinstance(parsed, dict):
                        return parsed
                    break
        start = cleaned.find("{", start + 1)

    raise LLMError("LLM did not return a parseable JSON object")


def build_llm_client(settings: Settings) -> LLMClient | None:
    """Build a client from settings, or ``None`` when no provider is configured.

    ``llm_provider="openai"`` means "OpenAI-compatible" and honours
    ``llm_base_url``. Any other provider returns ``None`` so callers fall back to
    their deterministic behaviour.
    """
    if settings.llm_provider != "openai":
        if settings.llm_provider != "none":
            _logger.warning("llm.unsupported_provider", provider=settings.llm_provider)
        return None
    api_key = settings.llm_api_key or settings.openai_api_key
    if not api_key:
        return None
    return LLMClient(
        base_url=settings.llm_base_url,
        api_key=api_key,
        model=settings.llm_model,
        timeout=settings.llm_timeout_seconds,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
        max_retries=settings.llm_max_retries,
    )
