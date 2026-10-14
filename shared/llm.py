"""Minimal OpenAI-compatible chat client shared by the agents.

Works with any OpenAI-compatible gateway (OpenAI, Azure-style proxies, or a
self-hosted router such as relaymodels) by pointing ``LLM_BASE_URL`` at the
``/v1`` endpoint. Uses httpx only, so no extra SDK is required.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from shared.config import UNITS_PER_USD, Settings
from shared.logging import get_logger

_logger = get_logger(__name__)

_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})

#: Reasons an :class:`LLMError` can carry, for log triage.
REASON_TIMEOUT = "timeout"
REASON_RATE_LIMITED = "rate_limited"
REASON_TRANSPORT = "transport"
REASON_BUDGET = "budget_exhausted"
REASON_EMPTY = "empty_response"
REASON_PARSE = "parse_error"
REASON_HTTP = "http_error"

# --- Provider pressure counters -------------------------------------------
# The gateway publishes no x-ratelimit-* headers, so a client cannot back off
# intelligently: it only observes a 429 or silence. These counters make the
# pressure visible from the other side, per process, so a cycle can be
# attributed rather than guessed at.
_stats: dict[str, int | float] = {
    "calls": 0,
    "attempts": 0,
    "retries": 0,
    "rate_limited": 0,
    "budget_exhausted": 0,
    "timeouts": 0,
    "failures": 0,
    # Token accounting. Recorded so spend can be attributed to a cycle from the
    # logs instead of only from the provider's dashboard, which cannot be
    # correlated with our correlation ids.
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "cached_tokens": 0,
    "total_tokens": 0,
    # Calls whose response carried no usage block. A gateway that omits usage
    # would otherwise make the token totals silently understate real spend.
    "usage_missing": 0,
    # Derived spend. ``cost_units`` is an exact integer in the provider's billing
    # unit; ``cost_usd`` is the same figure converted at UNITS_PER_USD and is
    # therefore fractional, so it is held as a float.
    "cost_units": 0,
    "cost_usd": 0.0,
}

#: Billing units charged per token billed, derived from the provider dashboard's
#: own arithmetic: every observed request showed ``(prompt + completion) * 4``
#: matching its recorded cost exactly (261->1044, 589->2356, 1166->4664,
#: 716->2864, and the cached row 246->984). Cached tokens are charged at the
#: same rate, so caching does not reduce cost under this pricing — it only cuts
#: latency.
COST_PER_TOKEN_UNITS = 4

#: Process-wide concurrency limiter, shared by every client built with the
#: same ``limit``. Keyed so the analysis and chat paths can be capped
#: independently; the first client to ask for a limit creates the semaphore.
_limiters: dict[int, asyncio.Semaphore] = {}


def llm_stats() -> dict[str, int | float]:
    """Snapshot of the provider-pressure, token and spend counters."""
    return dict(_stats)


def cache_hit_rate() -> float:
    """Fraction of prompt tokens served from the gateway's cache.

    Returns 0.0 when nothing has been billed yet, so a zero-token window reads
    as "no hits observed" rather than dividing by zero.
    """
    prompt = _stats["prompt_tokens"]
    if prompt <= 0:
        return 0.0
    return _stats["cached_tokens"] / prompt


def _record_usage(usage: Any, model: str) -> dict[str, int]:
    """Accumulate token usage from a response and log it.

    Returns the parsed counts so the caller can include them in its own log
    line. Gateways vary in what they report, so every field is optional and a
    missing usage block is counted rather than treated as zero — a silent zero
    would understate spend without any signal that it had.
    """
    if not isinstance(usage, dict):
        _stats["usage_missing"] += 1
        _logger.warning("llm.usage_missing", model=model)
        return {"prompt": 0, "completion": 0, "cached": 0, "total": 0}

    def _count(value: Any) -> int:
        return value if isinstance(value, int) and value >= 0 else 0

    details = usage.get("prompt_tokens_details")
    cached = _count(details.get("cached_tokens")) if isinstance(details, dict) else 0
    counts = {
        "prompt": _count(usage.get("prompt_tokens")),
        "completion": _count(usage.get("completion_tokens")),
        "cached": cached,
        "total": _count(usage.get("total_tokens")),
    }
    if not any(counts.values()):
        _stats["usage_missing"] += 1

    # Cached tokens are billed at the same rate as fresh ones, so cost is derived
    # from the full prompt count and cached tokens are not discounted.
    cost_units = (counts["prompt"] + counts["completion"]) * COST_PER_TOKEN_UNITS
    cost_usd = cost_units / UNITS_PER_USD

    _stats["prompt_tokens"] += counts["prompt"]
    _stats["completion_tokens"] += counts["completion"]
    _stats["cached_tokens"] += counts["cached"]
    _stats["total_tokens"] += counts["total"]
    _stats["cost_units"] += cost_units
    _stats["cost_usd"] += cost_usd

    _logger.info(
        "llm.usage",
        model=model,
        prompt_tokens=counts["prompt"],
        completion_tokens=counts["completion"],
        cached_tokens=counts["cached"],
        total_tokens=counts["total"],
        cost_units=cost_units,
        cost_usd=round(cost_usd, 8),
    )
    return counts


def reset_llm_stats() -> None:
    """Zero the counters. Intended for tests and for clean measurement windows."""
    for key in _stats:
        _stats[key] = 0.0 if key == "cost_usd" else 0


def _limiter_for(limit: int) -> asyncio.Semaphore | None:
    """Return the shared semaphore for ``limit``, or ``None`` when unbounded.

    Created lazily on first use so it binds to the running event loop; asyncio
    primitives must not be constructed at import time.
    """
    if limit <= 0:
        return None
    existing = _limiters.get(limit)
    if existing is None:
        existing = asyncio.Semaphore(limit)
        _limiters[limit] = existing
    return existing


class LLMError(Exception):
    """Raised when the LLM endpoint fails or returns an unusable response.

    Carries structured diagnostics so every fallback site can log *why* it
    degraded without re-deriving it. A fallback that produces plausible-looking
    output is otherwise indistinguishable from a real model response, which is
    how a slow provider went unnoticed behind ``confidence=0.5``.

    Args:
        message: Human-readable description.
        reason: One of the ``REASON_*`` constants.
        attempts: How many attempts were made before giving up.
        status: HTTP status code, when the failure came from a response.
    """

    def __init__(
        self,
        message: str,
        *,
        reason: str = REASON_HTTP,
        attempts: int = 1,
        status: int | None = None,
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.attempts = attempts
        self.status = status


@dataclass(frozen=True)
class LLMClient:
    """A thin OpenAI-compatible chat-completions client.

    Args:
        base_url: OpenAI-compatible root, e.g. ``https://host/v1``.
        api_key: Bearer token.
        model: Model identifier.
        timeout: Per-attempt ceiling in seconds.
        total_timeout: Cumulative ceiling across all attempts and backoff.
            ``None`` disables the budget, leaving ``timeout * (retries + 1)``
            as the worst case.
        max_concurrency: In-flight cap for this process when the client
            holds a limiter; ``None`` means unbounded.
    """

    base_url: str
    api_key: str
    model: str
    timeout: float = 30.0
    temperature: float = 0.2
    max_tokens: int = 512
    max_retries: int = 2
    total_timeout: float | None = None
    max_concurrency: int = 0
    limiter: asyncio.Semaphore | None = field(default=None, compare=False, repr=False)

    async def complete(self, prompt: str, *, system: str | None = None) -> str:
        """Send a chat completion and return the assistant message text.

        Retries transient failures (timeouts, 429 and 5xx) with a short backoff,
        bounded by ``total_timeout`` across every attempt. Holding
        ``max_concurrency`` for the whole retry loop is deliberate: a single
        logical call should occupy one slot for its lifetime rather than
        re-entering the queue between attempts, which would let a retry storm
        slip past the cap.

        Raises:
            LLMError: On an unrecoverable failure or an exhausted time budget.
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

        limiter = self.limiter
        if limiter is None and self.max_concurrency > 0:
            limiter = _limiter_for(self.max_concurrency)
        if limiter is not None:
            await limiter.acquire()
        try:
            return await self._attempt_loop(url, payload, headers)
        finally:
            if limiter is not None:
                limiter.release()

    async def _attempt_loop(
        self, url: str, payload: dict[str, Any], headers: dict[str, str]
    ) -> str:
        """Run the retry loop under the cumulative time budget."""
        deadline = (
            None if self.total_timeout is None else time.monotonic() + self.total_timeout
        )
        last_error: Exception | None = None
        last_status: int | None = None
        last_reason: str = REASON_HTTP
        attempts = 0

        for attempt in range(self.max_retries + 1):
            if deadline is not None and time.monotonic() >= deadline:
                _stats["budget_exhausted"] += 1
                _stats["failures"] += 1
                _logger.warning(
                    "llm.budget_exhausted",
                    model=self.model,
                    total_timeout=self.total_timeout,
                    attempts=attempts,
                    last_reason=last_reason,
                )
                raise LLMError(
                    f"LLM time budget of {self.total_timeout}s exhausted after "
                    f"{attempts} attempt(s)",
                    reason=REASON_BUDGET,
                    attempts=attempts,
                    status=last_status,
                ) from last_error

            attempts += 1
            _stats["attempts"] += 1
            _stats["calls"] += 1
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(url, json=payload, headers=headers)
                if response.status_code in _RETRYABLE_STATUS:
                    last_status = response.status_code
                    if response.status_code == 429:
                        last_reason = REASON_RATE_LIMITED
                        _stats["rate_limited"] += 1
                    _logger.warning(
                        "llm.retryable_status",
                        model=self.model,
                        status=response.status_code,
                        attempt=attempt + 1,
                        max_attempts=self.max_retries + 1,
                    )
                    if attempt < self.max_retries:
                        _stats["retries"] += 1
                        await self._backoff(attempt, deadline)
                        continue
                    _stats["failures"] += 1
                    raise LLMError(
                        f"HTTP {response.status_code}",
                        reason=last_reason,
                        attempts=attempts,
                        status=response.status_code,
                    )
                response.raise_for_status()
                data = response.json()
                # Called for its side effect: it accumulates the token counters
                # and logs the per-call usage. The cycle log reads llm_stats().
                _record_usage(data.get("usage"), self.model)
                message = data["choices"][0]["message"]
                content = message.get("content")
                if not isinstance(content, str) or not content.strip():
                    # Reasoning models sometimes leave content empty and put the
                    # text in reasoning_content; use it as a fallback.
                    content = message.get("reasoning_content")
                if not isinstance(content, str) or not content.strip():
                    _stats["failures"] += 1
                    raise LLMError(
                        "LLM returned an empty response",
                        reason=REASON_EMPTY,
                        attempts=attempts,
                    )
                return content.strip()
            except httpx.TimeoutException as exc:
                last_error = exc
                last_reason = REASON_TIMEOUT
                _stats["timeouts"] += 1
                if attempt < self.max_retries:
                    _stats["retries"] += 1
                    await self._backoff(attempt, deadline)
                    continue
            except httpx.TransportError as exc:
                last_error = exc
                last_reason = REASON_TRANSPORT
                if attempt < self.max_retries:
                    _stats["retries"] += 1
                    await self._backoff(attempt, deadline)
                    continue
            except LLMError:
                raise
            except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
                _stats["failures"] += 1
                raise LLMError(
                    f"LLM request failed: {exc!r}",
                    reason=REASON_PARSE if not isinstance(exc, httpx.HTTPError) else REASON_HTTP,
                    attempts=attempts,
                ) from exc

        _stats["failures"] += 1
        raise LLMError(
            f"LLM request failed after retries: {last_error!r}",
            reason=last_reason,
            attempts=attempts,
            status=last_status,
        )

    async def _backoff(self, attempt: int, deadline: float | None) -> None:
        """Sleep before the next attempt, clipped to the remaining budget."""
        delay = 1.5 * (attempt + 1)
        if deadline is not None:
            delay = min(delay, max(0.0, deadline - time.monotonic()))
        if delay > 0:
            await asyncio.sleep(delay)

    async def complete_json(self, prompt: str, *, system: str | None = None) -> dict[str, Any]:
        """Send a chat completion and parse a JSON object from the reply."""
        raw = await self.complete(prompt, system=system)
        try:
            return extract_json_object(raw)
        except LLMError as exc:
            raise LLMError(
                str(exc), reason=REASON_PARSE, attempts=exc.attempts, status=exc.status
            ) from exc


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

    This is the legacy ``llm_*`` gateway. Analysis agents that should run on the
    dedicated reasoning endpoint call :func:`build_analysis_llm_client` instead,
    and the assistant calls :func:`build_chat_llm_client`.
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
        total_timeout=settings.llm_total_timeout_seconds,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
        max_retries=settings.llm_max_retries,
    )


def build_chat_llm_client(settings: Settings) -> LLMClient | None:
    """Client for the conversational assistant (``/ai`` page).

    Uses the dedicated ``chat_llm_*`` settings so chat traffic is billed to the
    fast model and never competes with the analysis pipeline. Returns ``None``
    when no key is configured, letting callers degrade gracefully.
    """
    api_key = settings.chat_llm_api_key
    if not api_key:
        return None
    return LLMClient(
        base_url=settings.chat_llm_base_url,
        api_key=api_key,
        model=settings.chat_llm_model,
        timeout=settings.llm_timeout_seconds,
        total_timeout=settings.llm_total_timeout_seconds,
        temperature=settings.llm_temperature,
        max_tokens=settings.chat_llm_max_tokens,
        max_retries=settings.llm_max_retries,
    )


def build_analysis_llm_client(settings: Settings) -> LLMClient | None:
    """Primary client for the analysis agents, or ``None`` when unconfigured.

    The analysis pipeline (technical narrative, news sentiment, risk narrative
    and the decision reasoner) uses this so that when ``analysis_llm_api_key`` is
    set it runs on the dedicated reasoning endpoint in ``analysis_llm_base_url``.
    The first entry of ``analysis_llm_models`` is the primary reasoner; the rest
    are reserved as independent second opinions.

    When no analysis key is configured this falls back to the generic ``llm_*``
    gateway the agents have always used, so an existing install keeps working
    unchanged. ``None`` means neither is configured and callers should use their
    deterministic behaviour.
    """
    clients = build_analysis_llm_clients(settings)
    if clients:
        return clients[0]
    return build_llm_client(settings)


def build_analysis_llm_clients(settings: Settings) -> list[LLMClient]:
    """Clients for the analysis models, in preference order.

    The first configured model is the primary reasoner; the second is the
    independent second opinion used to validate the result.

    Requires ``analysis_llm_api_key`` specifically. The legacy ``llm_api_key`` is
    deliberately not borrowed here: it belongs to a different gateway, and
    sending it to ``analysis_llm_base_url`` would silently break an install that
    is working today.
    """
    api_key = settings.analysis_llm_api_key
    if not api_key:
        return []
    clients: list[LLMClient] = []
    for model in settings.analysis_llm_models:
        clients.append(
            LLMClient(
                base_url=settings.analysis_llm_base_url,
                api_key=api_key,
                model=model,
                # Previously max(llm_timeout_seconds, 180.0) with the comment
                # "reasoning models spend tokens on hidden reasoning". That floor
                # was a guess, and it cost three minutes per attempt: with
                # max_retries=2 a single logical call could occupy a worker for
                # 544s, which is how a provider rate-limit blip turned into a
                # multi-minute stall and a growing task queue. Measured latency
                # is 4-12s typical, so the per-attempt ceiling now comes from
                # analysis_llm_timeout_seconds and the cumulative ceiling from
                # llm_total_timeout_seconds, which is what actually bounds the
                # wall time.
                timeout=settings.analysis_llm_timeout_seconds,
                total_timeout=settings.llm_total_timeout_seconds,
                temperature=settings.llm_temperature,
                max_tokens=settings.llm_max_tokens,
                max_retries=settings.llm_max_retries,
                # Cap in-flight analysis calls at the single choke point every
                # agent shares, rather than at each call site.
                max_concurrency=settings.analysis_max_concurrent_llm,
            )
        )
    return clients
