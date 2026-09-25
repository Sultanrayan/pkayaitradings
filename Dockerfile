# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update \
    && apt-get install --no-install-recommends -y curl \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies first for better layer caching.
COPY pyproject.toml README.md ./
COPY shared ./shared
COPY agents ./agents
COPY data_pipeline ./data_pipeline
COPY execution ./execution
COPY orchestrator ./orchestrator
COPY migrations ./migrations
COPY alembic.ini ./

RUN --mount=type=cache,target=/root/.cache/pip pip install .

# Create /data owned by appuser so a freshly created named volume inherits the
# right ownership (Docker seeds a new volume from the image path), letting the
# non-root process persist the user/access-request stores there.
RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /data \
    && chown -R appuser:appuser /app /data
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS "http://localhost:${PORT:-8000}/health" || exit 1

# Shell form so the injected $PORT (Railway, Heroku, etc.) is honoured.
CMD uvicorn orchestrator.main:app --host 0.0.0.0 --port "${PORT:-8000}"
