"""Shared pytest fixtures."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from shared.config import Settings, get_settings


@pytest.fixture(autouse=True)
def _isolate_environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Keep the developer ``.env`` out of tests.

    Environment variables take precedence over the ``.env`` file, so setting
    the credential fields to neutral values makes the suite deterministic and
    prevents real network calls to the LLM or OAuth providers.

    The chat and analysis model credentials must be listed here too. Without
    them a developer who has ``CHAT_LLM_API_KEY`` or ``ANALYSIS_LLM_API_KEY`` in
    ``.env`` silently gets live, billed API calls from unit tests, and assertions
    on the deterministic template output start failing on real model prose.
    """
    for name in (
        "LLM_PROVIDER",
        "LLM_API_KEY",
        "LLM_BASE_URL",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "CHAT_LLM_API_KEY",
        "CHAT_LLM_BASE_URL",
        "ANALYSIS_LLM_API_KEY",
        "ANALYSIS_LLM_BASE_URL",
        "GOOGLE_CLIENT_ID",
        "GOOGLE_CLIENT_SECRET",
        "BREVO_API_KEY",
        "SMTP_LOGIN",
        "SMTP_PASSWORD",
    ):
        monkeypatch.setenv(name, "")
    monkeypatch.setenv("LLM_PROVIDER", "none")
    # Keep the suite hermetic: no real email delivery and no token enforcement.
    monkeypatch.setenv("AUTH_REQUIRED", "false")
    # The registration limiter is process-global state keyed by IP. Every request in
    # the suite arrives from the same TestClient address, so without this the suite
    # exhausts one shared bucket partway through and later tests fail with 429s
    # depending on ordering.
    monkeypatch.setenv("RECAPTCHA_SECRET_KEY", "")
    from orchestrator import antibot as _antibot

    if _antibot._REGISTER_LIMITER is not None:
        _antibot._REGISTER_LIMITER._entries.clear()
    get_settings.cache_clear()
    yield
    if _antibot._REGISTER_LIMITER is not None:
        _antibot._REGISTER_LIMITER._entries.clear()
    get_settings.cache_clear()


@pytest.fixture
def settings() -> Settings:
    """Deterministic settings for tests (no .env dependency)."""
    return Settings(
        environment="development",
        trading_symbols=["XAUUSD", "BTCUSD"],
        analysis_timeframes=["M5", "H1", "H4"],
        llm_provider="none",
        broker="paper",
        biquote_max_retries=2,
        biquote_requests_per_minute=1_000_000,
    )
