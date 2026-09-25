"""Typed application settings loaded from the environment.

Settings are immutable and cached, so importing :func:`get_settings` anywhere in
the codebase returns the same instance. Values are read from process environment
variables first, then from a local ``.env`` file (see ``.env.example``).
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from shared.schemas.enums import Timeframe


def _parse_list(value: object) -> object:
    """Accept a JSON array or a comma-separated string for list settings.

    pydantic-settings normally JSON-decodes complex fields from the environment;
    ``NoDecode`` fields are routed here so both ``a,b`` and ``["a","b"]`` work.
    """
    if not isinstance(value, str):
        return value
    text = value.strip()
    if text.startswith("["):
        try:
            parsed = json.loads(text)
        except ValueError:
            parsed = None
        if isinstance(parsed, list):
            return parsed
    return [item.strip() for item in text.split(",") if item.strip()]


class Settings(BaseSettings):
    """Runtime configuration for the whole system."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Runtime ---
    environment: Literal["development", "staging", "production"] = "development"
    log_level: str = "INFO"
    log_json: bool = False

    # --- Durable data ---
    # Directory where the JSON stores (users, access requests) are persisted.
    # Empty means in-memory only (development/tests). Production mounts a volume
    # here (e.g. DATA_DIR=/data) so accounts survive restarts and redeploys.
    data_dir: str = ""

    # --- Database ---
    postgres_url: str = "postgresql+asyncpg://trading:trading@localhost:5432/trading"

    # --- Redis ---
    redis_url: str = "redis://localhost:6379/0"

    # --- Qdrant ---
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str | None = None

    # --- biquote ---
    biquote_base_url: str = "https://biquote.io"
    biquote_timeout_seconds: float = 10.0
    biquote_max_retries: int = 3
    biquote_requests_per_minute: int = 15_000

    # --- Symbols & timeframes ---
    trading_symbols: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["XAUUSD", "BTCUSD"]
    )
    analysis_timeframes: Annotated[list[Timeframe], NoDecode] = Field(
        default_factory=lambda: [Timeframe.M5, Timeframe.H1, Timeframe.H4]
    )
    primary_timeframe: Timeframe = Timeframe.H1

    # --- LLM ---
    # "openai" means any OpenAI-compatible endpoint; point llm_base_url at your
    # gateway (for example https://api.relaymodels.com/v1).
    llm_provider: Literal["openai", "anthropic", "none"] = "none"
    llm_model: str = "gpt-4o-mini"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str | None = None
    # Reasoning models spend tokens on hidden reasoning, so keep a generous
    # budget and timeout.
    llm_timeout_seconds: float = 120.0
    llm_temperature: float = 0.2
    llm_max_tokens: int = 1500
    llm_max_retries: int = 2
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None

    # --- Broker / execution ---
    broker: Literal["paper", "mt5", "binance"] = "paper"
    paper_initial_balance: float = 100_000.0
    mt5_login: int | None = None
    mt5_password: str | None = None
    mt5_server: str | None = None
    binance_api_key: str | None = None
    binance_api_secret: str | None = None

    # --- Risk ---
    max_drawdown_pct: float = 0.05
    max_position_size: float = 0.5
    var_confidence: float = 0.95
    var_limit_pct: float = 0.02
    correlation_warn_threshold: float = 0.7
    kelly_fraction: float = 0.25
    risk_free_rate: float = 0.0

    # --- Decision engine ---
    weight_technical: float = 0.45
    weight_news: float = 0.25
    weight_risk: float = 0.30
    decision_buy_threshold: float = 0.65
    decision_skip_threshold: float = 0.35
    # "weighted" = legacy arithmetic weighted sum; "geometric" = weighted
    # geometric mean with hard consistency rules (backend-v2 roadmap).
    decision_aggregation: Literal["weighted", "geometric"] = "geometric"

    # --- Circuit breaker (backend-v2, Problem 2) ---
    # Per-agent resilience: after this many consecutive failures an agent's
    # circuit opens and calls are rejected until the recovery timeout elapses.
    circuit_breaker_failure_threshold: int = 5
    circuit_breaker_recovery_timeout_seconds: float = 300.0

    # --- Intelligence layer (backend-v2, Problems 7-10) ---
    order_flow_enabled: bool = True
    episodic_memory_enabled: bool = True
    hmm_regime_enabled: bool = True
    llm_review_enabled: bool = True

    # Order-flow imbalance analyzer (Problem 7).
    order_flow_delta_window: int = 20
    order_flow_divergence_lookback: int = 30

    # Episodic memory (Problem 8): similar-situation recall and win-rate scoring.
    memory_recall_k: int = 10
    memory_min_samples: int = 5
    memory_score_adjustment_max: float = 0.10

    # Gaussian HMM regime detector (Problem 9).
    hmm_n_states: int = 4
    hmm_n_iter: int = 50
    hmm_n_restarts: int = 3
    hmm_min_observations: int = 40

    # LLM chain-of-thought review (Problem 10): bounded confidence adjustment.
    llm_review_adjustment_max: float = 0.10

    # --- Plans & billing ---
    # Limits are per billing period (``plan_billing_period_days``); ``-1`` means
    # unlimited. Free = 20 analyses/month, Pro = 150/month, Ultra = unlimited.
    plan_free_monthly_limit: int = 20
    plan_pro_monthly_limit: int = 150
    plan_ultra_monthly_limit: int = -1
    plan_pro_price_usd: float = 15.0
    plan_ultra_price_usd: float = 65.0
    plan_billing_period_days: int = 30
    # Free Pro trial length (days) granted via the "Pro plan" / "gifts" flow.
    plan_trial_days: int = 60

    # --- Khpay (KHQR payments) ---
    # API key from khpay.site (``ak_...``). Empty disables checkout.
    khpay_api_key: str = ""
    khpay_base_url: str = "https://khpay.site/api/v1"
    khpay_webhook_secret: str = ""

    # --- Scheduler ---
    analysis_interval_seconds: int = 300

    # --- API gateway ---
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"]
    )
    # Serve FastAPI's /docs, /redoc and /openapi.json. Off by default so the API
    # surface is not enumerable from the browser; enable for local development.
    expose_api_docs: bool = False

    # --- Auth ---
    # When true, every /api/v1/* endpoint (except /api/v1/auth/*) requires a
    # bearer token. Disabled by default so local development and the test suite
    # work without accounts; enable in production.
    auth_required: bool = False
    auth_secret: str = "pkay-dev-insecure-secret-change-me"
    auth_token_ttl_seconds: int = 86_400

    # --- Google OAuth ---
    # Create an OAuth 2.0 Client ID (Web application) in Google Cloud Console and
    # add <api>/api/v1/auth/google/callback as an authorised redirect URI.
    google_client_id: str | None = None
    google_client_secret: str | None = None
    google_redirect_uri: str = "http://localhost:8000/api/v1/auth/google/callback"
    # Where the browser is sent after a successful Google sign-in.
    frontend_url: str = "http://localhost:3000"

    # --- Email (Brevo) ---
    # Preferred: Brevo's transactional email HTTP API (https://api.brevo.com/v3).
    # Set BREVO_API_KEY to an ``xkeysib-...`` key. The SMTP relay below is only
    # used as a fallback when no API key is configured.
    brevo_api_key: str = ""
    brevo_api_url: str = "https://api.brevo.com/v3/smtp/email"
    smtp_host: str = "smtp-relay.brevo.com"
    smtp_port: int = 587
    smtp_login: str = ""
    smtp_password: str = ""
    email_sender: str = "no-reply@pkay.fun"
    email_sender_name: str = "Pkay TDAI"
    public_base_url: str = "https://trade.pkay.fun"
    logo_url: str = "https://trade.pkay.fun/logo-pkay.jpg"

    # --- Cloudflare Turnstile ---
    # Extra bot check on account registration and developer applications.
    # Keys come from dash.cloudflare.com → Turnstile. Leave empty to disable.
    turnstile_site_key: str = ""
    turnstile_secret_key: str = ""
    turnstile_verify_url: str = "https://challenges.cloudflare.com/turnstile/v0/siteverify"

    # --- Admin ---
    admin_emails: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["menmengleapx1@gmail.com"]
    )

    @field_validator("admin_emails", mode="before")
    @classmethod
    def _parse_admin_emails(cls, value: object) -> object:
        """Accept a JSON array or comma-separated env var for admin emails."""
        parsed = _parse_list(value)
        if isinstance(parsed, list):
            return [str(item).strip().lower() for item in parsed]
        return parsed

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        """Accept a JSON array or comma-separated env var for CORS origins."""
        return _parse_list(value)

    @field_validator("trading_symbols", "analysis_timeframes", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        """Accept a JSON array or comma-separated env var for list fields."""
        return _parse_list(value)

    @field_validator("analysis_timeframes", mode="before")
    @classmethod
    def _coerce_timeframes(cls, value: object) -> object:
        """Upper-case timeframe strings before enum validation."""
        if isinstance(value, (list, tuple)):
            return [str(item).upper() for item in value]
        if isinstance(value, str):
            parsed = _parse_list(value)
            if isinstance(parsed, list):
                return [str(item).upper() for item in parsed]
        return value

    @field_validator("primary_timeframe", mode="before")
    @classmethod
    def _coerce_primary_timeframe(cls, value: object) -> object:
        """Upper-case the primary timeframe before enum validation."""
        if isinstance(value, str):
            return value.upper()
        return value

    @field_validator("trading_symbols")
    @classmethod
    def _normalise_symbols(cls, value: list[str]) -> list[str]:
        symbols = [symbol.upper() for symbol in value]
        if not symbols:
            raise ValueError("At least one trading symbol is required")
        return symbols

    @model_validator(mode="after")
    def _validate_weights(self) -> Settings:
        total = self.weight_technical + self.weight_news + self.weight_risk
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"Decision weights must sum to 1.0, got {total:.4f}")
        if not 0.0 < self.decision_skip_threshold < self.decision_buy_threshold < 1.0:
            raise ValueError("Require 0 < skip threshold < buy threshold < 1")
        return self

    @property
    def is_production(self) -> bool:
        """Whether the service is running in the production environment."""
        return self.environment == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide cached :class:`Settings` instance."""
    return Settings()
