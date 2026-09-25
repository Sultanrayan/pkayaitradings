"""Exceptions raised by the biquote data layer."""

from __future__ import annotations


class BiquoteError(Exception):
    """Base class for all biquote client errors."""


class BiquoteNotFoundError(BiquoteError):
    """Raised on HTTP 404 — unknown symbol or a quote older than 7 days."""


class BiquoteRateLimitedError(BiquoteError):
    """Raised on HTTP 429 after retries are exhausted.

    Attributes:
        retry_after: Seconds the server asked the caller to wait.
    """

    def __init__(self, message: str, retry_after: float = 60.0) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class BiquoteUnavailableError(BiquoteError):
    """Raised on HTTP 503 or a transport failure after retries are exhausted."""
