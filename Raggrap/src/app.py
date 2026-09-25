"""Standalone FastAPI application for the GraphRAG engine.

Serve with::

    uvicorn raggrap.src.app:app --reload
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from ..config.settings import settings as default_settings
from .api import router
from .core.graph_rag import GraphRAGEngine


def create_app(config: Any = None) -> FastAPI:
    """Build the standalone FastAPI app with a lifecycle-managed engine."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = GraphRAGEngine(config or default_settings)
        app.state.rag_engine = engine
        try:
            yield
        finally:
            engine.close()

    application = FastAPI(
        title=default_settings.app_name,
        version=default_settings.app_version,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )
    application.include_router(router)
    return application


app = create_app()
