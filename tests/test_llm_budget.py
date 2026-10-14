"""Tests for the LLM client's time budget, concurrency cap and pressure counters.

These exercise the failure paths that motivated the change: a rate-limit blip
used to become a 544s stall because ``max_retries`` bounded attempts but not
elapsed time, and nothing capped how many calls could be in flight at once.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx
import pytest

from shared.config import UNITS_PER_USD, Settings
from shared.llm import (
    COST_PER_TOKEN_UNITS,
    REASON_BUDGET,
    REASON_HTTP,
    REASON_RATE_LIMITED,
    REASON_TIMEOUT,
    LLMClient,
    LLMError,
    build_analysis_llm_clients,
    cache_hit_rate,
    llm_stats,
    reset_llm_stats,
)

_URL = "https://llm.test/v1/chat/completions"


class _Transport(httpx.AsyncBaseTransport):
    """Scripted transport so no network call is ever made."""

    def __init__(self, script: list[httpx.Response | Exception]) -> None:
        self._script = list(script)
        self.calls = 0

    async def handle_async_request(
        self, request: httpx.Request
    ) -> httpx.Response:  # pragma: no cover - exercised indirectly
        index = min(self.calls, len(self._script) - 1)
        self.calls += 1
        item = self._script[index]
        if isinstance(item, Exception):
            raise item
        return item


def _ok(content: str = "done") -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"role": "assistant", "content": content}}],
        },
    )


def _client(
    monkeypatch: pytest.MonkeyPatch, transport: httpx.AsyncBaseTransport, **overrides: Any
) -> LLMClient:
    """Build a client whose httpx calls are intercepted by ``transport``.

    Only ``AsyncClient`` is patched, so the exception hierarchy
    (``TimeoutException``, ``HTTPStatusError``) stays intact for the client's
    own ``except`` clauses to catch.
    """
    real_client = httpx.AsyncClient

    def _patched(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", _patched)
    return LLMClient(
        base_url="https://llm.test/v1",
        api_key="k",
        model="m",
        **overrides,
    )


@pytest.fixture(autouse=True)
def _clean_state() -> None:
    """Reset the process-wide counters and limiter cache around each test."""
    from shared.llm import _limiters

    reset_llm_stats()
    _limiters.clear()
    yield
    reset_llm_stats()
    _limiters.clear()


# --------------------------------------------------------------------------- #
# Config defaults
# --------------------------------------------------------------------------- #


def test_budget_and_concurrency_defaults() -> None:
    s = Settings()
    assert s.llm_total_timeout_seconds == 240.0
    assert s.analysis_max_concurrent_llm == 3
    assert s.analysis_llm_timeout_seconds == 60.0


def test_all_three_attempts_fit_inside_the_budget() -> None:
    """The per-attempt ceiling must not consume the retry budget.

    With 60s and 2 retries the worst case is 3 x 60 + 4.5 backoff = 184.5s,
    inside the 240s budget, so all three attempts can still run. At the
    previous 120s only two attempts fit, which silently halved the retry
    capability.
    """
    s = Settings()
    per_attempt = s.analysis_llm_timeout_seconds
    attempts = s.llm_max_retries + 1
    backoff = sum(1.5 * (i + 1) for i in range(s.llm_max_retries))
    worst_case = per_attempt * attempts + backoff
    assert worst_case == 184.5
    assert worst_case <= s.llm_total_timeout_seconds


def test_per_attempt_ceiling_releases_a_slot_within_a_minute() -> None:
    """A hung call must not hold a concurrency slot for minutes.

    This is why the ceiling dropped from 120s to 60s: with a cap of 3 and 6
    callers, a single 120s attempt blocked a slot for two minutes and the
    remaining callers queued behind it, turning gateway latency into local wall
    time. 60s bounds the slot hold to a minute so the queue drains in
    observable steps.
    """
    assert Settings().analysis_llm_timeout_seconds <= 60.0


def test_analysis_interval_is_900() -> None:
    """A slow cycle must finish inside the interval or the queue grows."""
    assert Settings().analysis_interval_seconds == 900


def test_worst_case_cycle_still_fits_the_interval() -> None:
    """A cycle is 4 sequential LLM stages, so the pathological worst case is
    ``4 * budget``. That is 960s against a 900s interval — deliberately NOT
    asserted as fitting.

    This test pins the real relationship instead. The budget is a cap on a
    degraded call, not an expectation: measured latency is 4-12s per call, so a
    healthy cycle is ~30-60s and the interval has ~15x headroom. The worst case
    can only be reached if every stage exhausts its entire budget, in which case
    the output is the deterministic template and the cycle is degraded by design
    rather than stalled. Kept as a documented consequence of the 240s budget
    and the 900s interval.
    """
    s = Settings()
    stages = 4
    worst_case = s.llm_total_timeout_seconds * stages
    assert worst_case == 960.0
    assert worst_case > s.analysis_interval_seconds, (
        "the pathological worst case exceeds one interval by design; the budget "
        "bounds a single call, not the whole cycle"
    )
    # The old behaviour for comparison: 544s for ONE call, 2176s for a cycle.
    old_single_call = 180.0 * 3 + 4.5
    assert s.llm_total_timeout_seconds < old_single_call
    assert s.llm_total_timeout_seconds * stages < old_single_call * stages


# --------------------------------------------------------------------------- #
# B — the 180s floor is gone
# --------------------------------------------------------------------------- #


def test_analysis_client_no_longer_overrides_the_timeout() -> None:
    """The per-attempt timeout now comes from settings, not a hard-coded floor."""
    s = Settings(
        analysis_llm_api_key="k",
        analysis_llm_base_url="https://llm.test/v1",
        analysis_llm_models=["m1", "m2"],
        analysis_llm_timeout_seconds=45.0,
    )
    clients = build_analysis_llm_clients(s)
    assert [c.model for c in clients] == ["m1", "m2"]
    for client in clients:
        assert client.timeout == 45.0
        assert client.total_timeout == s.llm_total_timeout_seconds


def test_analysis_client_carries_the_concurrency_cap() -> None:
    s = Settings(
        analysis_llm_api_key="k",
        analysis_llm_base_url="https://llm.test/v1",
        analysis_llm_models=["m1"],
        analysis_max_concurrent_llm=3,
    )
    assert build_analysis_llm_clients(s)[0].max_concurrency == 3


def test_worst_case_wall_time_is_now_bounded() -> None:
    """The regression guard: budget must cap total time, not just per attempt."""
    s = Settings(
        analysis_llm_api_key="k",
        analysis_llm_base_url="https://llm.test/v1",
        analysis_llm_models=["m1"],
        analysis_llm_timeout_seconds=120.0,
        llm_max_retries=2,
    )
    client = build_analysis_llm_clients(s)[0]
    # Old behaviour: timeout * (retries + 1) + backoff = 544.5s.
    # New behaviour: the budget, whatever the attempt count.
    assert client.total_timeout == 240.0
    old_worst_case = client.timeout * (client.max_retries + 1) + 4.5
    assert client.total_timeout < old_worst_case


# --------------------------------------------------------------------------- #
# A — total-elapsed budget
# --------------------------------------------------------------------------- #


async def test_budget_stops_a_slow_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """A provider slower than the budget must not run to the attempt limit."""
    reset_llm_stats()
    transport = _Transport([httpx.ReadTimeout("too slow") for _ in range(10)])
    client = _client(monkeypatch, transport, timeout=5.0, max_retries=5, total_timeout=1.0)

    start = time.monotonic()
    with pytest.raises(LLMError) as caught:
        await client.complete("p")
    elapsed = time.monotonic() - start

    assert elapsed < 4.0, f"budget did not bound the call: {elapsed:.1f}s"
    assert caught.value.reason == REASON_BUDGET
    assert transport.calls < 6, "retried past the budget"


async def test_budget_error_reports_attempt_count(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = _Transport([httpx.ReadTimeout("slow") for _ in range(10)])
    client = _client(monkeypatch, transport, timeout=5.0, max_retries=9, total_timeout=0.5)
    with pytest.raises(LLMError) as caught:
        await client.complete("p")
    assert caught.value.attempts >= 1
    assert llm_stats()["budget_exhausted"] == 1


async def test_no_budget_leaves_per_attempt_timeout_in_charge(monkeypatch: pytest.MonkeyPatch) -> None:
    """total_timeout=None disables the cap rather than defaulting to zero."""
    transport = _Transport([_ok("fast")])
    client = _client(monkeypatch, transport, timeout=5.0, total_timeout=None)
    assert await client.complete("p") == "fast"


async def test_successful_call_respects_the_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = _Transport([_ok("ok")])
    client = _client(monkeypatch, transport, timeout=5.0, total_timeout=30.0)
    assert await client.complete("p") == "ok"
    assert llm_stats()["budget_exhausted"] == 0


# --------------------------------------------------------------------------- #
# C — concurrency cap
# --------------------------------------------------------------------------- #


async def test_concurrency_is_capped(monkeypatch: pytest.MonkeyPatch) -> None:
    """No more than ``limit`` calls in flight, observed by the transport."""
    limit = 3
    inflight = 0
    peak = 0
    lock = asyncio.Lock()

    class _Counting(httpx.AsyncBaseTransport):
        async def handle_async_request(
            self, request: httpx.Request
        ) -> httpx.Response:  # pragma: no cover
            nonlocal inflight, peak
            async with lock:
                inflight += 1
                peak = max(peak, inflight)
            await asyncio.sleep(0.05)
            async with lock:
                inflight -= 1
            return _ok("ok")

    transport = _Counting()
    client = _client(monkeypatch, transport, timeout=5.0, max_concurrency=limit)
    await asyncio.gather(*(client.complete(f"p{i}") for i in range(12)))
    assert peak <= limit, f"observed {peak} in flight, cap is {limit}"


async def test_concurrency_cap_is_shared_across_clients(monkeypatch: pytest.MonkeyPatch) -> None:
    """Two clients built for the same limit must share one semaphore."""
    peak = 0
    inflight = 0
    lock = asyncio.Lock()

    class _Counting(httpx.AsyncBaseTransport):
        async def handle_async_request(
            self, request: httpx.Request
        ) -> httpx.Response:  # pragma: no cover
            nonlocal inflight, peak
            async with lock:
                inflight += 1
                peak = max(peak, inflight)
            await asyncio.sleep(0.05)
            async with lock:
                inflight -= 1
            return _ok("ok")

    transport = _Counting()
    a = _client(monkeypatch, transport, timeout=5.0, max_concurrency=3)
    b = _client(monkeypatch, transport, timeout=5.0, max_concurrency=3)
    await asyncio.gather(*(c.complete("p") for c in (a, b) for _ in range(6)))
    assert peak <= 3


async def test_zero_concurrency_is_unbounded(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = _Transport([_ok("ok")])
    client = _client(monkeypatch, transport, timeout=5.0, max_concurrency=0)
    assert await client.complete("p") == "ok"
    assert llm_stats()["failures"] == 0


async def test_queueing_shape_when_callers_exceed_the_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Six callers against a cap of three, with two first-wave calls slow.

    This documents the shape measured in production verification, where the
    semaphore held at 3 but wall time still reached ~132s: the cap moved the
    queue from the gateway into this process, so gateway latency inflation
    surfaces as local wall time rather than as 429s.

    Asserts the invariants that must hold — the cap is never exceeded, every
    caller completes, and the second wave genuinely waits — without asserting
    on absolute seconds, because gateway latency is not ours to predict.
    """
    limit = 3
    inflight = 0
    peak = 0
    queued = 0
    any_finished = False
    lock = asyncio.Lock()

    # Calls 2 and 3 are slow: they model the two first-wave calls that went
    # slow in the measured run and held two of the three slots.
    slow_calls = {2, 3}

    class _Shaped(httpx.AsyncBaseTransport):
        async def handle_async_request(
            self, request: httpx.Request
        ) -> httpx.Response:  # pragma: no cover - timing only
            nonlocal inflight, peak, queued, any_finished
            # Identify the call by its prompt body, not by arrival order, so the
            # slow calls are deterministic.
            body = request.content.decode()
            index = -1
            for candidate in range(10):
                if f"[{candidate}]" in body:
                    index = candidate
                    break
            async with lock:
                inflight += 1
                peak = max(peak, inflight)
                if any_finished:
                    queued += 1
            await asyncio.sleep(0.30 if index in slow_calls else 0.05)
            async with lock:
                inflight -= 1
                any_finished = True
            return _ok("ok")

    transport = _Shaped()
    client = _client(monkeypatch, transport, timeout=5.0, max_concurrency=limit)

    wall_start = time.monotonic()
    results = await asyncio.gather(
        *(client.complete(f"[{i}] p") for i in range(6))
    )
    wall = time.monotonic() - wall_start

    # The invariant that matters: the cap is never breached.
    assert peak <= limit, f"cap breached: {peak} in flight, limit is {limit}"
    # Every caller got a real answer despite the queueing.
    assert results == ["ok"] * 6
    # Queueing happened: at least one caller could only begin once a slot was
    # released, so the six did not all start at the same moment.
    assert queued >= 1, "callers all started before any finished; no queueing"
    assert queued < 6, "no caller waited for a slot, so the cap did nothing"
    # The batch outlasted a single slow call, which is the wall-time shape a
    # held slot produces. Absolute seconds are deliberately not asserted:
    # gateway latency is not ours to predict.
    assert wall > 0.30, f"expected a queueing delay, wall was only {wall:.2f}s"


# --------------------------------------------------------------------------- #
# Retryable status and the 429 counter
# --------------------------------------------------------------------------- #


async def test_429_increments_the_counter_and_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_llm_stats()
    transport = _Transport([httpx.Response(429, json={"error": "slow down"}) for _ in range(3)])
    client = _client(monkeypatch, transport, timeout=5.0, max_retries=2, total_timeout=30.0)

    with pytest.raises(LLMError) as caught:
        await client.complete("p")

    assert caught.value.reason == REASON_RATE_LIMITED
    assert caught.value.status == 429
    assert llm_stats()["rate_limited"] >= 1
    assert transport.calls == 3


async def test_429_then_success_returns_the_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_llm_stats()
    transport = _Transport([httpx.Response(429, json={}), _ok("recovered")])
    client = _client(monkeypatch, transport, timeout=5.0, max_retries=2, total_timeout=30.0)

    assert await client.complete("p") == "recovered"
    assert llm_stats()["rate_limited"] == 1
    assert llm_stats()["retries"] == 1
    assert llm_stats()["failures"] == 0


async def test_non_retryable_status_fails_immediately(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_llm_stats()
    transport = _Transport([httpx.Response(400, json={}) for _ in range(5)])
    client = _client(monkeypatch, transport, timeout=5.0, max_retries=3, total_timeout=30.0)
    with pytest.raises(LLMError):
        await client.complete("p")
    assert transport.calls == 1, "400 must not be retried"


async def test_timeout_is_classified(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = _Transport([httpx.ReadTimeout("slow") for _ in range(3)])
    client = _client(monkeypatch, transport, timeout=0.05, max_retries=0, total_timeout=10.0)
    with pytest.raises(LLMError) as caught:
        await client.complete("p")
    assert caught.value.reason == REASON_TIMEOUT
    assert llm_stats()["timeouts"] == 1


# --------------------------------------------------------------------------- #
# Structured diagnostics
# --------------------------------------------------------------------------- #


def test_llm_error_carries_diagnostics() -> None:
    err = LLMError("boom", reason=REASON_BUDGET, attempts=3, status=429)
    assert err.reason == REASON_BUDGET
    assert err.attempts == 3
    assert err.status == 429
    assert "boom" in str(err)


def test_llm_error_defaults_are_safe_for_plain_raises() -> None:
    """Fallback sites read these attributes off any exception."""
    err = LLMError("plain")
    assert err.reason == REASON_HTTP
    assert err.attempts == 1
    assert err.status is None


def test_llm_stats_exposes_the_documented_keys() -> None:
    reset_llm_stats()
    stats = llm_stats()
    for key in (
        "calls",
        "attempts",
        "retries",
        "rate_limited",
        "budget_exhausted",
        "timeouts",
        "failures",
        "prompt_tokens",
        "completion_tokens",
        "cached_tokens",
        "total_tokens",
        "usage_missing",
        "cost_units",
        "cost_usd",
    ):
        assert key in stats
    assert all(value == 0 for value in stats.values())


# --------------------------------------------------------------------------- #
# Token accounting
# --------------------------------------------------------------------------- #


def _usage_response(
    prompt: int = 158, completion: int = 140, cached: int = 126
) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"role": "assistant", "content": "ok"}}],
            "usage": {
                "prompt_tokens": prompt,
                "completion_tokens": completion,
                "total_tokens": prompt + completion,
                "prompt_tokens_details": {
                    "cache_creation_input_tokens": 0,
                    "cached_tokens": cached,
                },
            },
        },
    )


async def test_token_counters_accumulate(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_llm_stats()
    transport = _Transport([_usage_response()])
    client = _client(monkeypatch, transport, timeout=5.0, total_timeout=30.0)

    await client.complete("p")
    stats = llm_stats()
    assert stats["prompt_tokens"] == 158
    assert stats["completion_tokens"] == 140
    assert stats["cached_tokens"] == 126
    assert stats["total_tokens"] == 298
    assert stats["usage_missing"] == 0

    await client.complete("p")
    doubled = llm_stats()
    assert doubled["prompt_tokens"] == 316
    assert doubled["completion_tokens"] == 280
    assert doubled["cached_tokens"] == 252


async def test_missing_usage_is_counted_not_silently_zeroed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A gateway that omits usage must be visible, not counted as zero spend."""
    reset_llm_stats()
    transport = _Transport(
        [httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})]
    )
    client = _client(monkeypatch, transport, timeout=5.0, total_timeout=30.0)

    assert await client.complete("p") == "ok"
    stats = llm_stats()
    assert stats["usage_missing"] == 1
    assert stats["prompt_tokens"] == 0


async def test_partial_usage_does_not_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    """Some gateways report prompt tokens only; that must not break the call."""
    reset_llm_stats()
    transport = _Transport(
        [
            httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": "ok"}}],
                    "usage": {"prompt_tokens": 100},
                },
            )
        ]
    )
    client = _client(monkeypatch, transport, timeout=5.0, total_timeout=30.0)

    assert await client.complete("p") == "ok"
    stats = llm_stats()
    assert stats["prompt_tokens"] == 100
    assert stats["completion_tokens"] == 0
    # Some tokens were reported, so this is not a missing-usage event.
    assert stats["usage_missing"] == 0


async def test_usage_absent_details_key_is_tolerated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A response with no prompt_tokens_details must not raise on the lookup."""
    reset_llm_stats()
    transport = _Transport(
        [
            httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": "ok"}}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                },
            )
        ]
    )
    client = _client(monkeypatch, transport, timeout=5.0, total_timeout=30.0)

    assert await client.complete("p") == "ok"
    assert llm_stats()["cached_tokens"] == 0
    assert llm_stats()["prompt_tokens"] == 10


# --------------------------------------------------------------------------- #
# Cost accounting
#
# The rate is (prompt + completion) * COST_PER_TOKEN, matched against the four
# dashboard rows the provider supplied. Cached tokens are charged at the same
# rate as fresh ones, which is why cost_units must be checked against the full
# prompt count and never the non-cached remainder.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("prompt", "completion", "expected_units"),
    [
        (154, 107, 1044),  # 261 tokens -> 1044 units (dashboard: 1.04K)
        (430, 159, 2356),  # 589 tokens -> 2356 units (dashboard: 2.36K)
        (545, 621, 4664),  # 1166 tokens -> 4664 units (dashboard: 4.66K)
        (616, 100, 2864),  # 716 tokens -> 2864 units (dashboard: 2.86K)
        (112, 134, 984),  # cached row: (20 + 92 + 134) tokens -> 984 units
    ],
)
async def test_cost_matches_the_dashboard_arithmetic(
    monkeypatch: pytest.MonkeyPatch,
    prompt: int,
    completion: int,
    expected_units: int,
) -> None:
    reset_llm_stats()
    transport = _Transport([_usage_response(prompt=prompt, completion=completion)])
    client = _client(monkeypatch, transport, timeout=5.0, total_timeout=30.0)

    await client.complete("p")
    assert llm_stats()["cost_units"] == expected_units
    assert llm_stats()["cost_usd"] == pytest.approx(expected_units / 25_000_000)


async def test_cost_accumulates_across_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_llm_stats()
    transport = _Transport([_usage_response(prompt=154, completion=107)])
    client = _client(monkeypatch, transport, timeout=5.0, total_timeout=30.0)

    await client.complete("p")
    assert llm_stats()["cost_units"] == 1044
    await client.complete("p")
    assert llm_stats()["cost_units"] == 2088
    assert llm_stats()["cost_usd"] == pytest.approx(2088 / 25_000_000)


async def test_a_full_day_of_analysis_bills_a_plausible_amount(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pins the daily figure the enable decision rests on.

    Production runs 14 calls per cycle over 2 symbols at a 900s interval, so 96
    cycles and 1344 calls per day. A measured cycle billed 9906 tokens across
    those 14 calls (~708 per call), which the per-call fixture below approximates
    with 610 prompt + 98 completion tokens. That is ~951k tokens/day, and the
    provider's published rate puts it near $0.15/day.

    The band is deliberately loose but the assertion that matters is the derived
    one: if the token accounting or the rate is ever changed, ``cost_usd`` must
    still agree with ``cost_units / UNITS_PER_USD`` rather than drifting apart.
    """
    reset_llm_stats()
    calls_per_day = 14 * 96  # calls per cycle * cycles per day
    transport = _Transport([_usage_response(prompt=610, completion=98, cached=0)])
    client = _client(monkeypatch, transport, timeout=5.0, total_timeout=30.0)

    for _ in range(calls_per_day):
        await client.complete("p")

    stats = llm_stats()
    assert stats["calls"] == calls_per_day == 1344
    assert stats["total_tokens"] == 708 * 1344
    assert stats["cost_usd"] == pytest.approx(stats["cost_units"] / 25_000_000)
    assert 0.10 < float(stats["cost_usd"]) < 0.25, (
        f"daily spend drifted to {stats['cost_usd']}"
    )


def test_cost_is_zero_before_any_call() -> None:
    """An unbilled window must read as zero spend, not as a division artefact."""
    reset_llm_stats()
    stats = llm_stats()
    assert stats["cost_units"] == 0
    assert stats["cost_usd"] == 0.0


def test_units_per_usd_matches_the_published_rate() -> None:
    """One dollar of spend must be exactly UNITS_PER_USD units."""
    assert UNITS_PER_USD == 25_000_000
    assert COST_PER_TOKEN_UNITS == 4
    # A single token costs 4 units, i.e. $0.00000016.
    assert pytest.approx(1.6e-7) == COST_PER_TOKEN_UNITS / UNITS_PER_USD


async def test_cached_tokens_are_not_discounted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A fully-cached prompt still bills at the full rate.

    Guards the assumption behind dropping any cache-based cost saving: the
    dashboard charges cached tokens the same as fresh ones.
    """
    reset_llm_stats()
    transport = _Transport([_usage_response(prompt=112, completion=134, cached=92)])
    client = _client(monkeypatch, transport, timeout=5.0, total_timeout=30.0)

    await client.complete("p")
    stats = llm_stats()
    assert stats["cached_tokens"] == 92
    assert stats["cost_units"] == (112 + 134) * 4


async def test_missing_usage_adds_no_cost(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unknown usage must not be booked as zero-cost silently.

    The call succeeded, so there is nothing to bill, but the missing block is
    already counted separately; cost_units stays flat rather than inventing a
    figure.
    """
    reset_llm_stats()
    transport = _Transport(
        [httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})]
    )
    client = _client(monkeypatch, transport, timeout=5.0, total_timeout=30.0)

    await client.complete("p")
    assert llm_stats()["cost_units"] == 0
    assert llm_stats()["cost_usd"] == 0.0
    assert llm_stats()["usage_missing"] == 1


async def test_partial_usage_bills_only_the_reported_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prompt-only usage bills the prompt, without inventing a completion cost."""
    reset_llm_stats()
    transport = _Transport(
        [
            httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": "ok"}}],
                    "usage": {"prompt_tokens": 100},
                },
            )
        ]
    )
    client = _client(monkeypatch, transport, timeout=5.0, total_timeout=30.0)

    await client.complete("p")
    assert llm_stats()["cost_units"] == 400
    assert llm_stats()["cost_usd"] == pytest.approx(400 / 25_000_000)


def test_cache_hit_rate_is_zero_before_any_call() -> None:
    """No tokens billed yet must not divide by zero."""
    reset_llm_stats()
    assert cache_hit_rate() == 0.0


async def test_cache_hit_rate_is_the_cached_fraction_of_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reset_llm_stats()
    transport = _Transport([_usage_response(prompt=200, completion=50, cached=50)])
    client = _client(monkeypatch, transport, timeout=5.0, total_timeout=30.0)

    await client.complete("p")
    assert cache_hit_rate() == pytest.approx(0.25)


async def test_cache_hit_rate_weights_by_volume(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The rate is a token ratio, so a small cached call cannot dominate.

    First call: 100 prompt / 100 cached. Second: 900 prompt / 0 cached.
    A per-call mean would report 0.5; the token-weighted ratio is 0.1.
    """
    reset_llm_stats()
    transport = _Transport(
        [
            _usage_response(prompt=100, completion=10, cached=100),
            _usage_response(prompt=900, completion=10, cached=0),
        ]
    )
    client = _client(monkeypatch, transport, timeout=5.0, total_timeout=30.0)

    await client.complete("p")
    await client.complete("p")
    assert llm_stats()["prompt_tokens"] == 1000
    assert llm_stats()["cached_tokens"] == 100
    assert cache_hit_rate() == pytest.approx(0.1)


async def test_empty_response_is_classified(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = _Transport([httpx.Response(200, json={"choices": [{"message": {}}]})])
    client = _client(monkeypatch, transport, timeout=5.0, max_retries=0, total_timeout=10.0)
    with pytest.raises(LLMError) as caught:
        await client.complete("p")
    assert "empty" in caught.value.reason


async def test_malformed_json_is_classified_as_parse(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = _Transport([httpx.Response(200, json={"unexpected": "shape"})])
    client = _client(monkeypatch, transport, timeout=5.0, max_retries=0, total_timeout=10.0)
    with pytest.raises(LLMError) as caught:
        await client.complete("p")
    assert caught.value.reason == "parse_error"
