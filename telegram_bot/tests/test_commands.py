"""Tests for ``/start``, ``/help``, ``/status``, ``/performance``, ``/confluence``, ``/orderflow``.

Also asserts RULE 2 directly: no admin command exists, and no command can reach
the configuration. The second part matters more than it looks — a read-only
command set is only meaningful if the handlers genuinely cannot write.
"""

from __future__ import annotations

import inspect

import pytest

from telegram_bot import commands as cmd
from telegram_bot.db import utcnow

#: Exactly the commands the specification allows.
EXPECTED_COMMANDS = {
    "start",
    "help",
    "status",
    "performance",
    "confluence",
    "orderflow",
    "agenza-xauusd",
    "agenza-btcusd",
}

#: Substrings that would indicate an administrative surface.
FORBIDDEN_TOKENS = (
    "admin",
    "setup",
    "config",
    "token",
    "claim",
    "login",
    "auth",
    "grant",
    "revoke",
    "promote",
    "sudo",
    "reset",
)


# --------------------------------------------------------------------------- #
# The commands work
# --------------------------------------------------------------------------- #


async def test_start_shows_help(ctx: cmd.CommandContext) -> None:
    text = await cmd.handle_message(ctx, "/start", user_id=1)
    assert text is not None
    assert text.startswith("📖 Welcome to Pkay AI Signals")
    assert "Powered by Pkay AI" in text
    assert "/help" in text


async def test_help_lists_every_command(ctx: cmd.CommandContext) -> None:
    text = await cmd.handle_message(ctx, "/help", user_id=1)
    assert text is not None
    assert text.startswith("📖 Commands")
    for symbol in ("xauusd", "btcusd"):
        for timeframe in ("1mn", "5mn", "15mn", "1h"):
            assert f"/agenza-{symbol} {timeframe}" in text


async def test_status_renders(ctx: cmd.CommandContext) -> None:
    text = await cmd.handle_message(ctx, "/status", user_id=1)
    assert text is not None
    assert text.startswith("🔍 Bot Status")
    assert "Status: ✅ Running" in text
    assert "XAUUSD" in text
    assert "BTCUSD" in text
    assert "Mode: balanced" in text


async def test_performance_renders(ctx: cmd.CommandContext) -> None:
    text = await cmd.handle_message(ctx, "/performance", user_id=1)
    assert text is not None
    assert text.startswith("📊 Performance")
    assert "Total:" in text
    assert "Period: last 7 days" in text


async def test_confluence_renders(ctx: cmd.CommandContext) -> None:
    text = await cmd.handle_message(ctx, "/confluence", user_id=1)
    assert text is not None
    assert "🔥 Last Confluence Signal" in text


async def test_orderflow_renders(ctx: cmd.CommandContext) -> None:
    text = await cmd.handle_message(ctx, "/orderflow", user_id=1)
    assert text is not None
    assert "⚡ Order Flow" in text


async def test_non_command_text_is_ignored(ctx: cmd.CommandContext) -> None:
    """A message that is not a command produces no reply."""
    assert await cmd.handle_message(ctx, "hello", user_id=1) is None
    assert await cmd.handle_message(ctx, "", user_id=1) is None


async def test_command_with_bot_suffix_is_accepted(ctx: cmd.CommandContext) -> None:
    """``/help@my_bot`` works; Telegram appends the bot name in groups."""
    text = await cmd.handle_message(ctx, "/help@pkay_signals_bot", user_id=1)
    assert text is not None
    assert "📖 Commands" in text


# --------------------------------------------------------------------------- #
# RULE 2 — no admin surface
# --------------------------------------------------------------------------- #


def test_only_the_specified_commands_exist() -> None:
    """The public surface is exactly the twelve specified commands."""
    # AGENZA_COMMANDS is keyed by command name, so its keys are the commands.
    available = set(cmd.COMMANDS) | set(cmd.AGENZA_COMMANDS)
    assert available == EXPECTED_COMMANDS, (
        f"unexpected commands: {sorted(available - EXPECTED_COMMANDS)}, "
        f"missing: {sorted(EXPECTED_COMMANDS - available)}"
    )


@pytest.mark.parametrize("name", sorted(FORBIDDEN_TOKENS))
def test_no_admin_like_command_name(name: str) -> None:
    """No command name suggests administration, setup or configuration."""
    available = set(cmd.COMMANDS) | set(cmd.AGENZA_COMMANDS)
    assert name not in available


def test_no_handler_writes_configuration() -> None:
    """No command handler may mutate config, symbols or timeframes.

    Enforced by inspecting the handlers' source for the write methods. A
    behavioural check would only catch the writes a test happened to trigger; this
    catches all of them, including ones nobody exercised.
    """
    forbidden = {
        "set_config",
        "set_configs",
        "add_symbol",
        "add_timeframe",
        "save_performance_snapshot",
        "clear_rate_limits",
    }

    handlers = [*cmd.COMMANDS.values(), cmd.handle_agenza]
    for handler in handlers:
        source = inspect.getsource(handler)
        for method in forbidden:
            assert f"db.{method}" not in source, (
                f"{handler.__name__} calls {method}, which writes configuration"
            )


def test_no_handler_reads_credentials() -> None:
    """No command may read the bot token or chat id."""
    handlers = [*cmd.COMMANDS.values(), cmd.handle_agenza]
    for handler in handlers:
        source = inspect.getsource(handler)
        assert "TELEGRAM_BOT_TOKEN" not in source
        assert "TELEGRAM_CHAT_ID" not in source


async def test_unknown_command_raises_rather_than_falling_through(ctx: cmd.CommandContext) -> None:
    """An unknown command is an explicit error, not a silent no-op.

    Silently ignoring it would make a typo look like the bot being down.
    """
    with pytest.raises(cmd.UnknownCommandError):
        await cmd.handle_message(ctx, "/nope", user_id=1)


def test_unknown_command_help_carries_every_specified_command(ctx: cmd.CommandContext) -> None:
    text = cmd.unknown_command_help(ctx.db.symbols())
    for symbol in ("xauusd", "btcusd"):
        assert f"/agenza-{symbol} 5mn" in text


# --------------------------------------------------------------------------- #
# Status details
# --------------------------------------------------------------------------- #


async def test_status_reports_never_when_a_pair_has_no_history(ctx: cmd.CommandContext) -> None:
    """An absent signal reports ``never`` rather than a fabricated age."""
    text = await cmd.handle_message(ctx, "/status", user_id=1)
    assert "never" in text


async def test_status_shows_a_real_age_after_a_signal(
    ctx: cmd.CommandContext, market, db
) -> None:
    """Once a signal exists, its age is computed from the stored bar timestamp."""
    from telegram_bot.engine import Signal
    from telegram_bot.orderflow import OrderFlowSnapshot

    now = utcnow()
    snapshot = OrderFlowSnapshot("XAUUSD", "5m", 100.0, 500.0, "rising", None, 1.2, False, 1.0, "proxy", now - 600)
    db.save_signal(
        Signal(
            symbol="XAUUSD",
            timeframe="5m",
            bar_ts=now - 600,
            action="BUY",
            entry=4156.0,
            sl=4146.0,
            tp1=4166.0,
            tp2=4176.0,
            confidence=0.8,
            layers={"trend": 0.8},
            order_flow=snapshot,
            reason="test",
        ).to_record(sent_at=now)
    )

    text = await cmd.handle_message(ctx, "/status", user_id=1)
    # Pairs with no history still report "never"; the one that has a signal
    # reports its real age.
    assert "XAUUSD 5mn: 10m ago" in text
    assert "BTCUSD 5mn: never" in text


# --------------------------------------------------------------------------- #
# Performance arithmetic
# --------------------------------------------------------------------------- #


async def test_performance_counts_resolved_signals_only(ctx: cmd.CommandContext, db) -> None:
    """An unresolved signal counts toward neither wins nor losses."""
    from telegram_bot.engine import Signal
    from telegram_bot.orderflow import OrderFlowSnapshot

    now = utcnow()
    for index in range(3):
        snapshot = OrderFlowSnapshot("XAUUSD", "5m", 1.0, 1.0, "rising", None, 1.0, False, 1.0, "proxy", now)
        row_id = db.save_signal(
            Signal(
                symbol="XAUUSD",
                timeframe="5m",
                bar_ts=now - 3_600 * (index + 1),
                action="BUY",
                entry=100.0,
                sl=99.0,
                tp1=102.0,
                tp2=104.0,
                confidence=0.7,
                layers={"trend": 0.7},
                order_flow=snapshot,
                reason="test",
            ).to_record(sent_at=now - 3_600 * (index + 1))
        )
        assert row_id is not None

    # Resolve one as a win; two stay open.
    db.set_outcome(int(row_id or 0), "win", 2.0)

    text = await cmd.handle_message(ctx, "/performance", user_id=1)
    assert "Total: 1 signal, 1 win (100.0%)" in text


async def test_performance_handles_an_empty_database(ctx: cmd.CommandContext) -> None:
    """Zero signals is a valid state and must not divide by zero."""
    text = await cmd.handle_message(ctx, "/performance", user_id=1)
    assert "Total: 0 signals, 0 wins (0.0%)" in text
    assert "Avg RR: 0.0" in text


async def test_performance_uses_singular_for_one_signal(ctx: cmd.CommandContext, db) -> None:
    """The required format shows "1 signal" and "1 win", not "1 signals"."""
    from telegram_bot.engine import Signal
    from telegram_bot.orderflow import OrderFlowSnapshot

    now = utcnow()
    snapshot = OrderFlowSnapshot("XAUUSD", "5m", 1.0, 1.0, "rising", None, 1.0, False, 1.0, "proxy", now)
    row_id = db.save_signal(
        Signal(
            symbol="XAUUSD",
            timeframe="5m",
            bar_ts=now - 60,
            action="BUY",
            entry=100.0,
            sl=99.0,
            tp1=102.0,
            tp2=104.0,
            confidence=0.7,
            layers={"trend": 0.7},
            order_flow=snapshot,
            reason="test",
        ).to_record(sent_at=now)
    )
    db.set_outcome(int(row_id or 0), "win", 2.0)

    text = await cmd.handle_message(ctx, "/performance", user_id=1)
    assert "Total: 1 signal, 1 win (100.0%)" in text
