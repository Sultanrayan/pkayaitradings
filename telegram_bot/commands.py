"""Command handlers — the complete public surface.

RULE 2: there are no admin commands, no setup flow and no token claim. The
command set below is the whole interface, and each handler is read-only with the
sole exception of signal history, which the scanner writes.

Handlers take plain values rather than Telegram objects, so the whole surface is
testable without a bot instance and without a network. That is deliberate: a
command handler that can only be tested by talking to Telegram is a command
handler whose error paths never run.

Rate limits are applied by :func:`handle_message` before a handler is called, so
no handler can forget one.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from shared.logging import get_logger
from telegram_bot import formatter
from telegram_bot.confluence import Confluence
from telegram_bot.db import Database, utcnow
from telegram_bot.defaults import BotConfig
from telegram_bot.engine import describe_rejection, reward_to_risk
from telegram_bot.scanner import Scanner
from telegram_bot.timeframes import VALID_TIMEFRAMES_HINT, parse_user_timeframe

_logger = get_logger(__name__)

__all__ = [
    "COMMANDS",
    "RATE_LIMITS",
    "CommandContext",
    "RateLimitedError",
    "UnknownCommandError",
    "handle_agenza",
    "handle_confluence",
    "handle_help",
    "handle_message",
    "handle_orderflow",
    "handle_performance",
    "handle_start",
    "handle_status",
]

#: Per-minute limits, exactly as specified.
RATE_LIMITS: dict[str, int] = {
    "agenza-xauusd": 1,
    "agenza-btcusd": 1,
    "status": 10,
    "performance": 5,
    "confluence": 5,
    "orderflow": 5,
    "start": 30,
    "help": 30,
}

#: The default for anything not named above.
DEFAULT_RATE_LIMIT = 30

#: Window for every limit, in seconds.
RATE_WINDOW_SECONDS = 60

#: Performance window used by ``/performance``.
PERFORMANCE_PERIOD_DAYS = 7


class RateLimitedError(Exception):
    """Raised when a user exceeds a command's per-minute limit."""


class UnknownCommandError(Exception):
    """Raised when a command is not in the public set.

    Carries the help text so the reply and the ``/help`` output cannot drift apart.
    """


@dataclass
class CommandContext:
    """Everything a handler needs.

    Args:
        db: Database.
        config: Bot configuration.
        scanner: Scanner, used by ``/agenza`` and ``/status``.
        confluence: Last known confluence, for ``/confluence``.
    """

    db: Database
    config: BotConfig
    scanner: Scanner
    confluence: Confluence | None = None


#: A handler is either a plain function or a coroutine function. The dispatcher
#: awaits the result when it is awaitable, so both kinds live in one table.
Handler = Callable[[CommandContext], Any]


# --------------------------------------------------------------------------- #
# /start and /help
# --------------------------------------------------------------------------- #


def handle_start(ctx: CommandContext) -> str:
    """Render ``/start``."""
    return formatter.format_start(
        ctx.db.symbols(), ctx.db.timeframes_for(ctx.db.symbols()[0])
    )


def handle_help(ctx: CommandContext) -> str:
    """Render ``/help``."""
    return formatter.format_help(ctx.db.symbols())


# --------------------------------------------------------------------------- #
# /status
# --------------------------------------------------------------------------- #


def handle_status(ctx: CommandContext) -> str:
    """Render ``/status``.

    Reads only. The "Last signals" section reports ``never`` for a pair with no
    history rather than inventing an age.
    """
    now = utcnow()
    symbols = ctx.db.symbols()
    timeframes_by_symbol = {s: ctx.db.timeframes_for(s) for s in symbols}

    ages: list[tuple[str, str, int | None]] = []
    for symbol in symbols:
        for timeframe in timeframes_by_symbol[symbol]:
            last = ctx.db.last_signal_time(symbol, timeframe)
            ages.append((symbol, timeframe, None if last is None else now - last))

    day_start = now - 86_400
    resolved = ctx.db.outcomes_since(day_start)
    today_signals = ctx.db.signal_count_since(day_start)
    wins = sum(1 for row in resolved if row.outcome == "win")
    avg_rr = _average_rr(resolved)

    return formatter.format_status(
        uptime_seconds=ctx.scanner.uptime_seconds,
        symbols=symbols,
        timeframes_by_symbol=timeframes_by_symbol,
        last_signal_ages=ages,
        today_signals=today_signals,
        today_wins=wins,
        today_avg_rr=avg_rr,
        orderflow_enabled=ctx.config.orderflow_enabled,
        mode=ctx.config.mode,
        now_ts=now,
    )


def _average_rr(rows: list[Any]) -> float:
    """Mean reward-to-risk of resolved signals.

    Uses the shared :func:`reward_to_risk` so this average is always on the same
    basis as the RR printed on the card. Averages taken against a different
    target would understate every card's figure.
    """
    values = [reward_to_risk(row.entry, row.sl, row.tp2) for row in rows]
    return sum(values) / len(values) if values else 0.0


# --------------------------------------------------------------------------- #
# /performance
# --------------------------------------------------------------------------- #


def handle_performance(ctx: CommandContext) -> str:
    """Render ``/performance``.

    Computed live from the ``signals`` table over the trailing 7 days rather than
    read from the ``performance`` snapshot table, so the number shown is always
    current.
    """
    now = utcnow()
    since = now - PERFORMANCE_PERIOD_DAYS * 86_400

    per_pair: list[tuple[str, str, int, int]] = []
    for symbol in ctx.db.symbols():
        for timeframe in ctx.db.timeframes_for(symbol):
            rows = [
                r
                for r in ctx.db.signals_in_range(since, now, symbol=symbol)
                if r.timeframe == timeframe
            ]
            wins = sum(1 for r in rows if r.outcome == "win")
            per_pair.append((symbol, timeframe, len(rows), wins))

    confluence_rows = _confluence_stats(ctx, since, now)
    all_rows = ctx.db.signals_in_range(since, now)
    resolved = [r for r in all_rows if r.outcome in ("win", "loss")]
    wins = sum(1 for r in resolved if r.outcome == "win")
    avg_rr = _average_rr(resolved)

    scored = [r for r in resolved if r.pnl_pct is not None]
    best = None
    worst = None
    if scored:
        best_row = max(scored, key=lambda r: r.pnl_pct or 0.0)
        worst_row = min(scored, key=lambda r: r.pnl_pct or 0.0)
        from telegram_bot.timeframes import INTERNAL_TO_USER

        best = (
            f"{best_row.symbol} {INTERNAL_TO_USER.get(best_row.timeframe, best_row.timeframe)}",
            float(best_row.pnl_pct or 0.0),
        )
        worst = (
            f"{worst_row.symbol} {INTERNAL_TO_USER.get(worst_row.timeframe, worst_row.timeframe)}",
            float(worst_row.pnl_pct or 0.0),
        )

    return formatter.format_performance(
        per_pair=per_pair,
        confluence_rows=confluence_rows,
        total_signals=len(resolved),
        total_wins=wins,
        avg_rr=avg_rr,
        best=best,
        worst=worst,
        period_days=PERFORMANCE_PERIOD_DAYS,
        now_ts=now,
    )


def _confluence_stats(
    ctx: CommandContext, since: int, now: int
) -> list[tuple[str, int, int]]:
    """Per-group confluence counts, e.g. ``XAUUSD 5mn+15mn``."""
    import json

    buckets: dict[str, list[Any]] = {}
    for row in ctx.db.signals_in_range(since, now):
        if not row.is_confluence or not row.confluence_tfs:
            continue
        key = json.dumps(sorted(row.confluence_tfs))
        buckets.setdefault(key, []).append(row)

    from telegram_bot.timeframes import INTERNAL_TO_USER

    out: list[tuple[str, int, int]] = []
    for key, rows in buckets.items():
        members = json.loads(key)
        label = f"{rows[0].symbol} " + "+".join(
            INTERNAL_TO_USER.get(tf, tf) for tf in members
        )
        out.append((label, len(rows), sum(1 for r in rows if r.outcome == "win")))
    return out


# --------------------------------------------------------------------------- #
# /confluence
# --------------------------------------------------------------------------- #


def handle_confluence(ctx: CommandContext) -> str:
    """Render ``/confluence``."""
    if ctx.confluence is not None:
        return formatter.format_confluence(ctx.confluence)

    row = None
    for symbol in ctx.db.symbols():
        row = ctx.db.latest_signal(symbol, confluence_only=True)
        if row is not None:
            break

    if row is None:
        return formatter.format_no_confluence()

    from telegram_bot.engine import Signal
    from telegram_bot.orderflow import OrderFlowSnapshot

    signal = Signal(
        symbol=row.symbol,
        timeframe=row.timeframe,
        bar_ts=row.timestamp,
        action=row.action,  # type: ignore[arg-type]
        entry=row.entry,
        sl=row.sl,
        tp1=row.tp1,
        tp2=row.tp2,
        confidence=row.confidence,
        layers=dict(row.layers),
        order_flow=OrderFlowSnapshot.from_dict(row.order_flow or {}),
        reason=row.reason,
        is_confluence=True,
        confluence_tfs=row.confluence_tfs,
    )
    members = tuple(row.confluence_tfs)
    pseudo = Confluence(
        symbol=row.symbol,
        action=row.action,
        timeframes=members,
        confidence=row.confidence,
        representative=row,
        members=(row,),
    )
    del signal
    return formatter.format_confluence(pseudo)


# --------------------------------------------------------------------------- #
# /orderflow
# --------------------------------------------------------------------------- #


async def handle_orderflow(ctx: CommandContext) -> str:
    """Render ``/orderflow`` for every symbol.

    Reads cached frames only. A fetch here would make this the slowest command in
    the bot for data the scanner already has.
    """
    from telegram_bot.orderflow import OrderFlowSnapshot, compute_order_flow

    pairs = ctx.db.all_pairs()
    rendered: list[tuple[str, Any]] = []
    seen: set[str] = set()

    for symbol, timeframe in pairs:
        if symbol in seen:
            continue
        frame = ctx.scanner.market.cached_frame(symbol, timeframe)
        if frame is None or frame.empty:
            continue
        try:
            snapshot: OrderFlowSnapshot = compute_order_flow(
                frame, symbol=symbol, timeframe=timeframe, position=-1
            )
        except Exception as exc:
            _logger.warning("orderflow.failed", symbol=symbol, error=repr(exc))
            continue
        rendered.append((symbol, snapshot))
        seen.add(symbol)

    if not rendered:
        return (
            "⚡ Order Flow — Live\n"
            + formatter.SEPARATOR
            + "\nNo order-flow data cached yet.\n"
            + "The scanner populates it on its first pass.\n\n"
            + f"Time: {formatter._timestamp(utcnow())}\n"
            + formatter.BRAND
        )

    return formatter.format_orderflow(rendered)


# --------------------------------------------------------------------------- #
# /agenza-<symbol> <timeframe>
# --------------------------------------------------------------------------- #


async def handle_agenza(ctx: CommandContext, symbol: str, timeframe_token: str) -> str:
    """Analyze one symbol and timeframe.

    Args:
        ctx: Handler context.
        symbol: Instrument ticker from the command name.
        timeframe_token: The user-facing timeframe token, e.g. ``5mn``.

    Returns:
        The analysis block, with the signal card appended when one fired.

    Raises:
        ValueError: For an unknown symbol or timeframe. The dispatcher turns this
            into a usage hint rather than a traceback.
    """
    upper = symbol.upper()
    known = ctx.db.symbols()
    if upper not in known:
        # Name the symbols that do exist, so a typo is recoverable without
        # consulting /help.
        raise ValueError(
            f"Unknown symbol: {upper}. Available: {', '.join(known)}"
        )

    internal = parse_user_timeframe(timeframe_token)
    if internal is None:
        raise ValueError(
            f"Unknown timeframe: {timeframe_token}. "
            f"Use one of: {VALID_TIMEFRAMES_HINT}"
        )

    if internal not in ctx.db.timeframes_for(upper):
        raise ValueError(f"{upper} is not configured for {internal}")

    now = utcnow()
    frame = await ctx.scanner.market.closed_frame(upper, internal)

    from telegram_bot.engine import compute_signal
    from telegram_bot.layers import compute_layers

    signal = compute_signal(
        frame, symbol=upper, timeframe=internal, config=ctx.config, now=now
    )

    if signal is not None:
        layers = compute_layers(
            frame.iloc[: _position_of(frame, signal.bar_ts)],
            symbol=upper,
            timeframe=internal,
            position=-1,
        ).results
        return formatter.format_analysis(
            symbol=upper,
            timeframe=internal,
            layers=layers,
            signal=signal,
            reason=signal.reason,
            bar_ts=signal.bar_ts,
        )

    rejection = describe_rejection(
        frame, symbol=upper, timeframe=internal, config=ctx.config, now=now
    )
    return formatter.format_analysis(
        symbol=upper,
        timeframe=internal,
        layers=rejection["layers"],
        signal=None,
        reason=rejection["reason"],
        bar_ts=_last_bar_ts(frame),
    )


def _position_of(frame: Any, bar_ts: int) -> int:
    """Positional index of a bar timestamp within a frame."""
    import pandas as pd

    from telegram_bot.engine import bar_close_seconds

    times = pd.Index(bar_close_seconds(frame.index))
    found = int(times.get_indexer([bar_ts])[0])
    return found if found >= 0 else len(frame)


def _last_bar_ts(frame: Any) -> int:
    """Close time of the frame's final bar, or 0 when empty."""
    if frame is None or frame.empty:
        return 0
    return int(frame.index[-1].timestamp())


# --------------------------------------------------------------------------- #
# Dispatch
# --------------------------------------------------------------------------- #

#: Command name -> handler, for the non-agenza commands. The agenza commands are
#: dispatched separately because they carry an argument.
#:
#: ``orderflow`` is a coroutine function while the rest are plain functions, so the
#: dispatcher awaits whatever a handler returns when it is awaitable. Keeping both
#: kinds in one table is what stops a command being implemented but never
#: registered — which is how ``/orderflow`` ended up missing from this dict once.
COMMANDS: dict[str, Handler] = {
    "start": handle_start,
    "help": handle_help,
    "status": handle_status,
    "performance": handle_performance,
    "confluence": handle_confluence,
    "orderflow": handle_orderflow,
}

#: Command name -> symbol, so ``/agenza-xauusd`` maps to ``XAUUSD``.
#:
#: Keyed by command name rather than by symbol, because that is how dispatch
#: looks it up. Keying by symbol (the earlier version) made every agenza command
#: fall through to "unknown command" — the map existed and was never reachable.
AGENZA_COMMANDS: dict[str, str] = {"agenza-xauusd": "XAUUSD", "agenza-btcusd": "BTCUSD"}


def rate_limit_for(command: str) -> int:
    """Per-minute limit for a command name."""
    return RATE_LIMITS.get(command, DEFAULT_RATE_LIMIT)


async def handle_message(ctx: CommandContext, text: str, user_id: int) -> str | None:
    """Route a message to a handler.

    Args:
        ctx: Handler context.
        text: Raw message text starting with ``/``.
        user_id: Telegram user id, for rate limiting.

    Returns:
        The reply text, or ``None`` when the message was silently rate-limited.

    Raises:
        UnknownCommandError: For a command outside the public set.
    """
    tokens = (text or "").strip().split()
    if not tokens or not tokens[0].startswith("/"):
        return None

    name = tokens[0][1:].split("@")[0].lower()
    args = tokens[1:]

    limit = rate_limit_for(name)
    if not ctx.db.check_rate_limit(user_id, name, limit, RATE_WINDOW_SECONDS):
        _logger.info("command.rate_limited", user_id=user_id, command=name, limit=limit)
        return None

    if name.startswith("agenza-"):
        if len(args) != 1:
            raise UnknownCommandError(
                f"Usage: /{name} <{VALID_TIMEFRAMES_HINT}>"
            )
        # A symbol with no configured command still gets a proper "unknown
        # symbol" answer rather than "unknown command", so a typo is recoverable.
        symbol = AGENZA_COMMANDS.get(name, name.removeprefix("agenza-").upper())
        return await handle_agenza(ctx, symbol, args[0])

    handler = COMMANDS.get(name)
    if handler is None:
        raise UnknownCommandError(f"Unknown command: /{name}")

    result = handler(ctx)
    if inspect.isawaitable(result):
        result = await result
    return str(result)


def unknown_command_help(symbols: list[str]) -> str:
    """Reply for an unrecognised command — the full help, since help is the answer."""
    return formatter.format_help(symbols)
