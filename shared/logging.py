"""Structured logging configuration for the whole system.

Call :func:`configure_logging` once at process start (the orchestrator and Celery
worker do this for you). Use :func:`get_logger` to obtain a bound logger.

Every rendered line passes through :func:`scrub_secrets`. That is not
belt-and-braces: ``httpx`` logs one INFO line per HTTP request containing the full
URL, and a Telegram bot token lives in that URL. Without a scrub in the shared
formatter the token is written to stdout, captured by ``docker logs``, and shipped
to any log aggregator — which is exactly how a credential that is carefully kept
out of the database ends up everywhere anyway.
"""

from __future__ import annotations

import logging
import re
import sys
from typing import Any

import structlog

_CONFIGURED = False

#: Credentials that must never reach a log line. Two shapes are covered because
#: two libraries produce them: a Telegram bot token is ``<digits>:<secret>``, and
#: most provider keys are a long opaque string. The token pattern has no leading
#: word boundary on purpose — in ``/bot123456:AAAA...`` the character before the
#: digits is a word character, so ``\b`` finds no transition and would miss the
#: single most common place to see one.
_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\d{5,}:[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\b(?:sk|pk|rk)-[A-Za-z0-9_-]{16,}\b"),
)

_REDACTED = "<redacted>"


def _scrub_value(value: Any) -> Any:
    """Recursively replace credential-shaped substrings in a log payload."""
    if isinstance(value, dict):
        for key, item in value.items():
            value[key] = _scrub_value(item)
        return value

    if isinstance(value, logging.LogRecord):
        value.msg = _scrub_value(value.msg)
        if isinstance(value.args, tuple):
            value.args = tuple(_scrub_value(a) for a in value.args)
        return value

    if isinstance(value, tuple):
        return tuple(_scrub_value(item) for item in value)

    if isinstance(value, str):
        scrubbed = value
        for pattern in _SECRET_PATTERNS:
            scrubbed = pattern.sub(_REDACTED, scrubbed)
        return scrubbed

    return value


def scrub_secrets(logger: Any, name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """structlog processor: scrub this project's own log events.

    structlog calls processors with ``(logger, method_name, event_dict)``, which is
    a different arity from ``foreign_pre_chain`` — hence a separate entry point
    rather than one variadic function that would hide which contract it meets.

    Args:
        logger: The bound logger.
        name: The log method name.
        event_dict: The assembled event.

    Returns:
        The same event dict, scrubbed.
    """
    scrubbed: dict[str, Any] = _scrub_value(event_dict)
    return scrubbed


def scrub_foreign_record(
    logger: Any, name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Alias of :func:`scrub_secrets` for the foreign-record chain.

    ``ProcessorFormatter.foreign_pre_chain`` uses the *same*
    ``(logger, name, event_dict)`` contract as the structlog chain — the record
    has already been folded into an event dict by the time processors run. So one
    implementation covers both, and this alias exists only to make the intent
    explicit at the call site where it is registered.

    Third-party records are the ones that matter: ``httpx`` logs the full request
    URL at INFO, and for the Telegram API the bot token *is* that URL.
    """
    return scrub_secrets(logger, name, event_dict)


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
        # Last in the structlog chain, so it sees the fully assembled event dict —
        # including anything format_exc_info folded a traceback into.
        scrub_secrets,
    ]

    # Third-party records arrive through a separate chain with a different
    # processor arity, so they get their own scrubber. This is the one that
    # matters: httpx writes the request URL, token included, at INFO.
    foreign_processors: list[Any] = [
        *shared_processors[:-1],
        scrub_foreign_record,
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

    # httpx emits one INFO line per request containing the full URL, which for the
    # Telegram API includes the bot token. It is high-volume noise whose only
    # effect here is to write the credential to disk, so it is silenced rather
    # than trusted to be scrubbed. Errors still come through, at WARNING.
    for noisy in ("httpx", "httpcore", "telegram.ext.Updater", "apscheduler.executors"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

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
        foreign_pre_chain=foreign_processors,
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
