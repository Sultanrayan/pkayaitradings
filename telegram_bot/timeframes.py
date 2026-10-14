"""Timeframe naming and bar arithmetic.

The bot has two spellings for every timeframe and mixing them up is the easiest
way to plot a signal on the wrong bar:

* **User spelling** — what someone types after ``/agenza-xauusd``: ``1mn``,
  ``5mn``, ``15mn``, ``1h``.
* **Internal spelling** — what is stored, scheduled and computed with: ``1m``,
  ``5m``, ``15m``, ``1h``.

All conversion goes through this module so there is exactly one mapping, and the
labels a user sees (``1M``, ``5M``, ``15M``, ``1H``) come from one place too.
"""

from __future__ import annotations

from telegram_bot.defaults import DEFAULT_TIMEFRAMES

__all__ = [
    "INTERNAL_TO_USER",
    "TIMEFRAME_SECONDS",
    "USER_TO_INTERNAL",
    "USER_TO_LABEL",
    "bar_close_time",
    "bar_seconds",
    "is_internal",
    "is_user",
    "parse_user_timeframe",
    "timeframes_for_scan",
]

#: Duration of one bar in seconds, keyed by internal name.
TIMEFRAME_SECONDS: dict[str, int] = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "1h": 3_600,
}

#: User spelling -> internal.
USER_TO_INTERNAL: dict[str, str] = {
    "1mn": "1m",
    "5mn": "5m",
    "15mn": "15m",
    "1h": "1h",
}

#: Internal -> user spelling, for display in command output.
INTERNAL_TO_USER: dict[str, str] = {
    internal: user for user, internal in USER_TO_INTERNAL.items()
}

#: Display label used in message headers, e.g. ``XAUUSD 5M``.
USER_TO_LABEL: dict[str, str] = {
    "1mn": "1M",
    "5mn": "5M",
    "15mn": "15M",
    "1h": "1H",
}

#: Suggestion text shown when a user supplies an unrecognised timeframe.
VALID_TIMEFRAMES_HINT = "1mn, 5mn, 15mn, 1h"


def parse_user_timeframe(raw: str) -> str | None:
    """Convert a user-supplied timeframe to its internal name.

    Matching is case-insensitive and tolerant of surrounding whitespace, because a
    user typing ``5MN`` or `` 5mn `` meant ``5mn``. The internal spelling (``5m``)
    is accepted too: it is the form used in the database and in the URL, so
    someone copying from either place should not be told they are wrong.

    Args:
        raw: The token the user typed.

    Returns:
        The internal timeframe, or ``None`` when unrecognised. ``None`` is the
        signal the caller uses to answer with a usage hint rather than guessing.
    """
    cleaned = raw.strip().lower()
    mapped = USER_TO_INTERNAL.get(cleaned)
    if mapped is not None:
        return mapped
    return cleaned if cleaned in TIMEFRAME_SECONDS else None


def is_user(raw: str) -> bool:
    """Whether ``raw`` is a recognised timeframe token in either spelling."""
    return parse_user_timeframe(raw) is not None


def is_internal(raw: str) -> bool:
    """Whether ``raw`` is a recognised internal timeframe."""
    return raw.strip().lower() in TIMEFRAME_SECONDS


def label_for(internal: str) -> str:
    """Display label for an internal timeframe, e.g. ``5m`` -> ``5M``.

    Falls back to the upper-cased input for anything unrecognised, so a label is
    always produced and a message is never missing its timeframe.
    """
    user = INTERNAL_TO_USER.get(internal)
    if user is None:
        return internal.upper()
    return USER_TO_LABEL.get(user, user.upper())


def bar_seconds(internal: str) -> int:
    """Duration of one bar in seconds.

    Raises:
        ValueError: For an unrecognised timeframe. Callers that accept user input
            must go through :func:`parse_user_timeframe` first.
    """
    key = internal.strip().lower()
    try:
        return TIMEFRAME_SECONDS[key]
    except KeyError as exc:
        raise ValueError(f"unsupported timeframe: {internal!r}") from exc


def bar_close_time(open_ts: int, internal: str) -> int:
    """Unix seconds at which a bar that opened at ``open_ts`` closes."""
    return int(open_ts) + bar_seconds(internal)


def timeframes_for_scan(internal: str) -> list[str]:
    """Timeframes whose bar closes at or before ``internal``'s bar close.

    Used by the confluence check: a 15m signal may only be confluent with 1h once
    the hour bar has actually closed, never on a partially-formed higher bar.
    """
    seconds = bar_seconds(internal)
    return [tf for tf in DEFAULT_TIMEFRAMES if bar_seconds(tf) <= seconds]
