"""Time helpers used across the system."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from shared.schemas.enums import Timeframe

_TF_DELTA: dict[Timeframe, timedelta] = {
    Timeframe.M1: timedelta(minutes=1),
    Timeframe.M5: timedelta(minutes=5),
    Timeframe.M15: timedelta(minutes=15),
    Timeframe.M30: timedelta(minutes=30),
    Timeframe.H1: timedelta(hours=1),
    Timeframe.H4: timedelta(hours=4),
    Timeframe.D1: timedelta(days=1),
}


def utcnow() -> datetime:
    """Timezone-aware current UTC time."""
    return datetime.now(UTC)


def timeframe_delta(timeframe: Timeframe) -> timedelta:
    """Return the wall-clock duration of a single bar for ``timeframe``."""
    return _TF_DELTA[timeframe]


def parse_iso8601(value: str) -> datetime:
    """Parse an ISO-8601 string, tolerating a trailing ``Z``.

    Raises:
        ValueError: If ``value`` is not a valid ISO-8601 timestamp.
    """
    normalised = value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalised)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def format_duration(delta: timedelta) -> str:
    """Render a duration as ``"2h 15m"`` / ``"45m"`` / ``"30s"``."""
    total_seconds = int(delta.total_seconds())
    if total_seconds < 0:
        total_seconds = 0
    hours, remainder = divmod(total_seconds, 3_600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m"
    return f"{seconds}s"
