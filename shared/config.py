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

#: Provider billing units per US dollar, as published by the gateway's pricing.
#: Together with :data:`shared.llm.COST_PER_TOKEN_UNITS` this converts the token
#: counters into a real spend figure:
#:
#:     cost_units = (prompt_tokens + completion_tokens) * COST_PER_TOKEN_UNITS
#:     cost_usd   = cost_units / UNITS_PER_USD
#:
#: A module constant rather than a :class:`Settings` field because it is a fact
#: about the provider, not about this deployment — no environment variable
#: should be able to silently misprice every log line. If the provider changes
#: its rate, this constant is the one place to correct.
UNITS_PER_USD = 25_000_000

#: Addresses allowed into the admin console when ``ADMIN_EMAILS`` is unset or blank.
#: Kept as a constant so the default and the blank-value fallback in
#: ``Settings._parse_admin_emails`` cannot drift apart.
DEFAULT_ADMIN_EMAILS: tuple[str, ...] = ("superpkay@gmail.com",)


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
    # --- Chat / query assistant (the `/ai` page) ---
    # Separate from the analysis stack: chat is served by a fast, cheap model
    # while analyses use the reasoning models below. Keys stay server-side and
    # are never exposed to the browser.
    chat_llm_model: str = "deepseek-v4.1-flash"
    chat_llm_base_url: str = "https://api.relaymodels.com/v1"
    chat_llm_api_key: str | None = None
    chat_llm_max_tokens: int = 2000

    # --- Analysis models ---
    # Reasoning pass and the reviewing/second-opinion pass used by the
    # analysis pipeline.
    # Parsed from JSON in the environment, e.g.
    # ANALYSIS_LLM_MODELS=["claude-opus-4-8","claude-opus-5-5"]
    analysis_llm_models: list[str] = Field(
        default_factory=lambda: ["claude-opus-4-8", "claude-opus-5-5"]
    )
    analysis_llm_base_url: str = "https://ru.cheapvibecode.ru/v1"
    analysis_llm_api_key: str | None = None

    llm_timeout_seconds: float = 120.0
    # Hard ceiling on the cumulative wall time of one ``complete()`` call
    # across every retry attempt and backoff. Without this, ``llm_max_retries``
    # bounds attempts but not elapsed time, so a single logical call could
    # occupy a worker for timeout * (retries + 1) — measured at 544s, against a
    # 300s analysis interval. The budget converts that stall into a bounded
    # failure that degrades to the deterministic template.
    llm_total_timeout_seconds: float = 240.0
    # Per-attempt timeout for the analysis models. Measured latency to the
    # gateway is 4-12s typical, ~33s at 6 concurrent and ~64s at 10; 429s
    # appear above roughly 6 concurrent. An earlier 180s floor meant one retry
    # could burn three minutes, and a 120s ceiling held a concurrency slot for
    # two minutes, which serialised behind the semaphore instead of failing
    # over. At 60s a slow call degrades to the template within a minute while
    # all three attempts still fit inside llm_total_timeout_seconds
    # (3 x 60 + 4.5 backoff = 184.5s), so retries are not sacrificed.
    analysis_llm_timeout_seconds: float = 60.0
    # Maximum analysis LLM calls in flight per process. The gateway rate-limits
    # on concurrency: 0/429 observed at 6 concurrent, 2/10 at 10. Capping here
    # bounds pressure at the single choke point every agent call passes through.
    # Note this is per process, so N worker processes allow N * this many; the
    # analysis interval is what normally keeps a single cycle in one worker.
    analysis_max_concurrent_llm: int = 3
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
    # Every plan has two independent caps and both are enforced: a daily cap that
    # resets at 00:00 UTC, and a cap per billing period
    # (``plan_billing_period_days``). A request is refused when either is reached.
    # ``-1`` means unlimited.
    #
    #   plan      daily   monthly   price
    #   free         2        60      $0
    #   starter      8       240      $6
    #   pro         20       600     $13
    #   ultra      250     7 500    $250
    plan_free_daily_limit: int = 2
    plan_free_monthly_limit: int = 60
    plan_starter_daily_limit: int = 8
    plan_starter_monthly_limit: int = 240
    plan_pro_daily_limit: int = 20
    plan_pro_monthly_limit: int = 600
    plan_ultra_daily_limit: int = 250
    plan_ultra_monthly_limit: int = 7500
    plan_starter_price_usd: float = 6.0
    plan_pro_price_usd: float = 13.0
    plan_ultra_price_usd: float = 250.0
    plan_billing_period_days: int = 30

    # --- Anti-bot (credential endpoints) ---
    # Google reCAPTCHA v2 protects login and register.
    #
    # The secret is server-side only: it is never returned by an endpoint, never
    # logged and never sent to the browser. The frontend reads the *site* key as
    # NEXT_PUBLIC_RECAPTCHA_SITE_KEY. An empty secret disables verification so local
    # development and the test suite keep working.
    recaptcha_secret_key: str = ""
    recaptcha_verify_url: str = "https://www.google.com/recaptcha/api/siteverify"
    # A submission faster than this was almost certainly scripted, and one older than
    # this is a replayed timestamp.
    recaptcha_min_form_seconds: float = 2.0
    recaptcha_max_form_seconds: float = 86_400.0
    # Per-IP ceilings on the credential endpoints, as a fixed window. Sized for a shared
    # address rather than a single user: an office, a university or a mobile carrier
    # can put hundreds of people behind one IP, so a tight ceiling would block real
    # sign-ups. Sign-in is additionally covered by LoginRateLimiter, which counts
    # failures and blocks for an hour.
    auth_login_attempts_per_window: int = 10
    auth_register_attempts_per_window: int = 10
    auth_rate_limit_window_seconds: int = 900

    # --- Khpay (KHQR payments) ---
    # API key from khpay.site (``ak_...``). Empty disables checkout.
    khpay_api_key: str = ""
    khpay_base_url: str = "https://khpay.site/api/v1"
    khpay_webhook_secret: str = ""

    # --- Zenmux (agenza XAU/USD classifier) ---
    #
    # Base URL and routes are fixed by the endpoint guide (`endpoint-guide.md`).
    # The key is server-side only: it is never sent to the browser, never placed
    # in a URL, and never logged. An empty key disables the feature, which the
    # API reports as a 503 rather than degrading to an invented prediction.
    #
    # Measured performance, for anyone reading this before trusting an output:
    # ROC-AUC 0.51-0.53 under purged walk-forward validation (random is 0.50),
    # and the cost-aware backtest is negative for both backends. A returned
    # probability is the model's output, not a calibrated odds of profit.
    zenmux_base_url: str = "https://router.pkay.fun/v1/agenza"
    zenmux_api_key: str = ""
    zenmux_default_backend: str = "xgboost"
    zenmux_default_threshold: float = 0.5

    # --- Scheduler ---
    # 900s, not 300s. A cycle is 4 sequential LLM stages (technical x3
    # concurrent, then news, risk, decision). At 300s a slow cycle cannot
    # finish before the next one is scheduled, so the queue grows without
    # bound and each overlapping cycle adds provider pressure. Loosen only
    # after sustained operation with no rate limiting.
    analysis_interval_seconds: int = 900

    # --- Signal engine (signals/) ---
    # The bar-anchored signal engine is a separate subsystem from the four-agent
    # cycle: it reads closed candles and emits BUY/SELL, and it never touches the
    # LLM. Ships disabled so it can be deployed and observed before it starts
    # publishing into the store the dashboard reads.
    signal_engine_enabled: bool = False
    # Confidence threshold profile. See ``signals.models.CONFIDENCE_THRESHOLDS``:
    # aggressive 0.40, balanced 0.60, conservative 0.75.
    signal_engine_mode: Literal["aggressive", "balanced", "conservative"] = "balanced"
    # Bars per symbol per pass. The engine's own cooldown also applies, so the
    # effective signal rate is the lower of the two.
    signal_engine_interval_seconds: int = 900
    # Minimum bars between two signals for the same symbol and timeframe.
    signal_engine_min_bars_between_signals: int = 5
    # Candles fetched per symbol. Must comfortably exceed the engine's warmup,
    # which is bounded by ema_slow (200).
    signal_engine_lookback: int = 400

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

    # --- RAG engine (GraphRAG self-improvement layer) ---
    # Exposes the ``Raggrap`` engine under ``/api/v1/raggrap``. The engine reuses
    # the main LLM settings (``llm_provider``/``llm_model``/``llm_base_url``) so
    # corrections retrieved from past mistakes guardrail the same model.
    raggrap_enabled: bool = True
    raggrap_main_llm_model: str = "gpt-4o"
    raggrap_critic_llm_model: str = "gpt-4o-mini"
    raggrap_max_related_mistakes: int = 5
    raggrap_cache_enabled: bool = True
    raggrap_cache_ttl: int = 3600

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
        default_factory=lambda: list(DEFAULT_ADMIN_EMAILS)
    )

    @field_validator("admin_emails", mode="before")
    @classmethod
    def _parse_admin_emails(cls, value: object) -> object:
        """Accept a JSON array or comma-separated env var for admin emails.

        An unset *or blank* value falls back to :data:`DEFAULT_ADMIN_EMAILS` rather
        than an empty list. Compose normally passes ``ADMIN_EMAILS=${ADMIN_EMAILS:-}``,
        which arrives as an empty string whenever the operator has cleared the
        variable; reading that as "nobody is an admin" would lock every administrator
        out of the console, which is the opposite of what clearing the override is
        meant to do.
        """
        parsed = _parse_list(value)
        if isinstance(parsed, list):
            cleaned = [str(item).strip().lower() for item in parsed if str(item).strip()]
            return cleaned if cleaned else list(DEFAULT_ADMIN_EMAILS)
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
