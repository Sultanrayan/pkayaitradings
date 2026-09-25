"""Structured logging configuration for the whole system.

Call :func:`configure_logging` once at process start (the orchestrator and Celery
worker do this for you). Use :func:`get_logger` to obtain a bound logger.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

_CONFIGURED = False


def configure_logging(
    *,
    level: str = "INFO",
    json_logs: bool = False,
) -> None:
    """Configure ``structlog`` and the stdlib root logger.

    Args:
        level: Log level name (e.g. ``"INFO"``, ``"DEBUG"``).
        json_logs: Emit one JSON object per line when ``True``; use a
            human-readable console renderer otherwise.
    """
    global _CONFIGURED

    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        timestamper,
    ]

    renderer: Any = (
        structlog.processors.JSONRenderer()
        if json_logs
        else structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())
    )

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level.upper(), logging.INFO),
        force=True,
    )

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )
    for handler in logging.getLogger().handlers:
        handler.setFormatter(formatter)

    _CONFIGURED = True


def get_logger(name: str | None = None, **initial_context: Any) -> structlog.stdlib.BoundLogger:
    """Return a bound structlog logger.

    Args:
        name: Logger name, typically ``__name__``.
        **initial_context: Key/value pairs bound to every emitted record.
    """
    if not _CONFIGURED:
        configure_logging()
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    if initial_context:
        logger = logger.bind(**initial_context)
    return logger
