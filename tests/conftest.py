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
    """
    for name in (
        "LLM_PROVIDER",
        "LLM_API_KEY",
        "LLM_BASE_URL",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
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
    get_settings.cache_clear()
    yield
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
