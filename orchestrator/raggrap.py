"""Backend integration for the Raggrap GraphRAG self-improvement engine.

The engine lives in the ``Raggrap`` package and is mounted into the main
FastAPI app under ``/api/v1/raggrap``. Corrections recorded from past mistakes
guardrail the same LLM gateway configured for the agents, so the RAG layer
shares the existing ``LLM_*`` environment settings.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from Raggrap.config.settings import Settings as RagSettings
from Raggrap.src.api import router as raggrap_router
from Raggrap.src.core.graph_rag import GraphRAGEngine
from shared.config import Settings
from shared.logging import get_logger

__all__ = ["build_raggrap_engine", "raggrap_router"]

_logger = get_logger(__name__)


def _parse_redis_url(url: str) -> dict[str, Any]:
    """Split a ``redis://`` URL into fields accepted by Raggrap settings."""
    parts = urlsplit(url)
    return {
        "redis_host": parts.hostname or "",
        "redis_port": parts.port or 6379,
        "redis_password": parts.password or None,
        "redis_db": int(parts.path.lstrip("/") or 0),
    }


def _map_settings(settings: Settings) -> RagSettings:
    """Map the backend app settings onto the Raggrap engine settings.

    The RAG engine reuses the same LLM provider/gateway as the agents so the
    guardrail corrections apply to the model actually serving answers.
    """
    provider = settings.llm_provider
    openai_api_key = settings.llm_api_key or settings.openai_api_key
    anthropic_api_key = settings.anthropic_api_key

    # "openai" in the backend means any OpenAI-compatible endpoint; forward the
    # base URL so the engine talks to the same gateway (e.g. a proxy).
    if provider == "openai" and openai_api_key:
        rag_provider = "openai"
        openai_base_url = settings.llm_base_url
    elif provider == "anthropic" and anthropic_api_key:
        rag_provider = "anthropic"
        openai_base_url = None
    else:
        # No usable key: use the offline deterministic provider so the API
        # stays live without any LLM configured (dev/tests).
        rag_provider = "none"
        openai_api_key = None
        openai_base_url = None

    return RagSettings(
        openai_api_key=openai_api_key,
        anthropic_api_key=anthropic_api_key,
        openai_base_url=openai_base_url,
        llm_provider=rag_provider,
        main_llm_model=settings.raggrap_main_llm_model,
        critic_llm_model=settings.raggrap_critic_llm_model,
        llm_temperature=0.0,
        llm_max_tokens=settings.llm_max_tokens,
        enable_cache=settings.raggrap_cache_enabled,
        cache_ttl=settings.raggrap_cache_ttl,
        max_related_mistakes=settings.raggrap_max_related_mistakes,
        **_parse_redis_url(settings.redis_url),
    )


def build_raggrap_engine(settings: Settings, **kwargs: Any) -> GraphRAGEngine:
    """Construct a :class:`GraphRAGEngine` wired to the backend settings."""
    config = _map_settings(settings)
    engine = GraphRAGEngine(config, **kwargs)
    _logger.info("raggrap.engine_ready", graph_store=type(engine.graph_store).__name__)
    return engine
