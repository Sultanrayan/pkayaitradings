"""Tests for the eight ``/agenza`` commands, their validation, and rate limits."""

from __future__ import annotations

import pytest

from telegram_bot import commands as cmd

#: Every valid user-facing timeframe token, per the specification.
VALID_TOKENS = ("1mn", "5mn", "15mn", "1h")

#: Internal names each must resolve to.
EXPECTED_INTERNAL = {"1mn": "1m", "5mn": "5m", "15mn": "15m", "1h": "1h"}

#: Symbols the bot is configured for.
VALID_SYMBOLS = ("xauusd", "btcusd")


# --------------------------------------------------------------------------- #
# Every specified command works
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("symbol", VALID_SYMBOLS)
@pytest.mark.parametrize("token", VALID_TOKENS)
async def test_every_agenza_command_works(
    ctx: cmd.CommandContext, market, symbol: str, token: str
) -> None:
    """All eight combinations produce an analysis block for the right pair."""
    from telegram_bot.tests.conftest import make_frame
    from telegram_bot.timeframes import TIMEFRAME_SECONDS

    internal = EXPECTED_INTERNAL[token]
    market.set_frame(
        symbol.upper(),
        internal,
        make_frame(300, seconds=TIMEFRAME_SECONDS[internal]),
    )

    text = await cmd.handle_message(ctx, f"/agenza-{symbol} {token}", user_id=100 + len(token))

    assert text is not None
    assert text.startswith("🔍 Analysis —")
    assert symbol.upper() in text
    # The display label, not the raw token: "5M", not "5mn".
    assert text.splitlines()[0].endswith(("1M", "5M", "15M", "1H"))
    assert "Powered by Pkay AI" in text


@pytest.mark.parametrize("symbol", VALID_SYMBOLS)
@pytest.mark.parametrize("token", VALID_TOKENS)
async def test_analysis_shows_all_five_display_layers(
    ctx: cmd.CommandContext, market, symbol: str, token: str
) -> None:
    """Every analysis block carries the five layers the required format shows."""
    from telegram_bot.tests.conftest import make_frame
    from telegram_bot.timeframes import TIMEFRAME_SECONDS

    internal = EXPECTED_INTERNAL[token]
    market.set_frame(
        symbol.upper(), internal, make_frame(300, seconds=TIMEFRAME_SECONDS[internal])
    )
    text = await cmd.handle_message(ctx, f"/agenza-{symbol} {token}", user_id=200 + len(token))

    assert text is not None
    for label in ("Trend:", "Momentum:", "Order Flow:", "Volume:", "Volatility:"):
        assert label in text
    assert "█" in text or "░" in text


async def test_analysis_includes_the_signal_card_when_one_fires(
    ctx: cmd.CommandContext, market
) -> None:
    """A firing signal appends the full card below the analysis block."""
    from telegram_bot.tests.conftest import make_frame

    market.set_frame("XAUUSD", "5m", make_frame(300, drift=0.006, noise=0.0005, seed=31))
    text = await cmd.handle_message(ctx, "/agenza-xauusd 5mn", user_id=301)

    assert text is not None
    has_card = "BUY — XAUUSD 5M" in text or "SELL — XAUUSD 5M" in text
    has_none = "Signal: ❌ No signal" in text
    assert has_card or has_none


async def test_no_signal_variant_explains_itself(ctx: cmd.CommandContext, market) -> None:
    """The no-signal branch always states a reason, never a bare "no signal"."""
    from telegram_bot.tests.conftest import make_frame

    market.set_frame("XAUUSD", "5m", make_frame(300, drift=-0.00005, noise=0.004, seed=37))
    text = await cmd.handle_message(ctx, "/agenza-xauusd 5mn", user_id=302)

    assert text is not None
    if "Signal: ❌ No signal" in text:
        assert "Reason:" in text
        assert "Confidence:" in text


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #


async def test_invalid_timeframe_is_rejected(ctx: cmd.CommandContext) -> None:
    """An unknown token raises, which the dispatcher turns into a usage hint."""
    with pytest.raises(ValueError, match=r"(?i)unknown timeframe"):
        await cmd.handle_message(ctx, "/agenza-xauusd 30mn", user_id=401)


async def test_invalid_symbol_is_rejected(ctx: cmd.CommandContext) -> None:
    with pytest.raises(ValueError, match=r"(?i)unknown symbol"):
        await cmd.handle_message(ctx, "/agenza-ethusd 5mn", user_id=402)


async def test_rejection_messages_list_the_valid_options(ctx: cmd.CommandContext) -> None:
    """A rejected argument must say what is accepted, not just that it is not."""
    with pytest.raises(ValueError) as symbol_error:
        await cmd.handle_message(ctx, "/agenza-ethusd 5mn", user_id=403)
    assert "XAUUSD" in str(symbol_error.value)
    assert "BTCUSD" in str(symbol_error.value)

    with pytest.raises(ValueError) as timeframe_error:
        await cmd.handle_message(ctx, "/agenza-xauusd 30mn", user_id=404)
    for token in ("1mn", "5mn", "15mn", "1h"):
        assert token in str(timeframe_error.value)


async def test_missing_timeframe_argument_is_rejected(ctx: cmd.CommandContext) -> None:
    """``/agenza-xauusd`` with no token is a usage error, not a silent default."""
    with pytest.raises(cmd.UnknownCommandError, match="Usage"):
        await cmd.handle_message(ctx, "/agenza-xauusd", user_id=403)


async def test_too_many_arguments_is_rejected(ctx: cmd.CommandContext) -> None:
    with pytest.raises(cmd.UnknownCommandError, match="Usage"):
        await cmd.handle_message(ctx, "/agenza-xauusd 5mn 15mn", user_id=404)


@pytest.mark.parametrize("token", ["1M", "5MN", " 5mn ", "5m"])
async def test_timeframe_matching_is_tolerant(
    ctx: cmd.CommandContext, market, token: str
) -> None:
    """Case and surrounding whitespace are forgiven; the value is not."""
    from telegram_bot.tests.conftest import make_frame

    market.set_frame("XAUUSD", "5m", make_frame(300))
    text = await cmd.handle_message(ctx, f"/agenza-xauusd {token}", user_id=500)
    assert text is not None
    assert "XAUUSD" in text


# --------------------------------------------------------------------------- #
# Rate limits
# --------------------------------------------------------------------------- #


async def test_agenza_is_limited_to_one_per_minute(ctx: cmd.CommandContext, market) -> None:
    """The second call inside the window is silently dropped, not errored."""
    from telegram_bot.tests.conftest import make_frame

    market.set_frame("XAUUSD", "5m", make_frame(300))

    first = await cmd.handle_message(ctx, "/agenza-xauusd 5mn", user_id=601)
    second = await cmd.handle_message(ctx, "/agenza-xauusd 5mn", user_id=601)

    assert first is not None
    assert second is None, "the second call in the window should be suppressed"


async def test_rate_limit_is_per_symbol(ctx: cmd.CommandContext, market) -> None:
    """The two agenza commands have separate buckets."""
    from telegram_bot.tests.conftest import make_frame

    market.set_frame("XAUUSD", "5m", make_frame(300))
    market.set_frame("BTCUSD", "5m", make_frame(300))

    gold = await cmd.handle_message(ctx, "/agenza-xauusd 5mn", user_id=602)
    bitcoin = await cmd.handle_message(ctx, "/agenza-btcusd 5mn", user_id=602)

    assert gold is not None
    assert bitcoin is not None, "a different command must have its own budget"


async def test_rate_limit_is_per_user(ctx: cmd.CommandContext, market) -> None:
    """One user exhausting a limit must not affect another."""
    from telegram_bot.tests.conftest import make_frame

    market.set_frame("XAUUSD", "5m", make_frame(300))

    assert await cmd.handle_message(ctx, "/agenza-xauusd 5mn", user_id=700) is not None
    assert await cmd.handle_message(ctx, "/agenza-xauusd 5mn", user_id=700) is None
    assert await cmd.handle_message(ctx, "/agenza-xauusd 5mn", user_id=701) is not None


async def test_status_allows_more_than_one_call_per_minute(ctx: cmd.CommandContext) -> None:
    """``/status`` has a 10/min budget, so a few calls all succeed."""
    results = [await cmd.handle_message(ctx, "/status", user_id=800) for _ in range(5)]
    assert all(r is not None for r in results)


async def test_status_limit_eventually_engages(ctx: cmd.CommandContext) -> None:
    """After the budget is spent, calls are suppressed rather than erroring."""
    results = [await cmd.handle_message(ctx, "/status", user_id=801) for _ in range(12)]
    assert any(r is None for r in results), "the 10/min limit never engaged"


async def test_help_limit_is_the_default_thirty(ctx: cmd.CommandContext) -> None:
    """``/help`` sits on the 30/min default."""
    results = [await cmd.handle_message(ctx, "/help", user_id=900) for _ in range(31)]
    assert results[0] is not None
    assert results[-1] is None


def test_rate_limits_match_the_specification() -> None:
    """The limit table is exactly as specified."""
    assert cmd.RATE_LIMITS["agenza-xauusd"] == 1
    assert cmd.RATE_LIMITS["agenza-btcusd"] == 1
    assert cmd.RATE_LIMITS["status"] == 10
    assert cmd.RATE_LIMITS["performance"] == 5
    assert cmd.RATE_LIMITS["confluence"] == 5
    assert cmd.RATE_LIMITS["orderflow"] == 5
    assert cmd.DEFAULT_RATE_LIMIT == 30
    assert cmd.RATE_WINDOW_SECONDS == 60


async def test_manual_analysis_ignores_the_auto_alert_cooldown(
    ctx: cmd.CommandContext, market, db, config
) -> None:
    """A user asking for an analysis gets an answer even during a cooldown.

    The cooldown exists to stop automatic spam. It must not silence a person who
    explicitly asked.

    Uses a permissive threshold because the subject is the delivery path, not the
    score. At the default 0.60 a synthetic trend correctly produces nothing — RSI
    saturates and momentum votes against the trend — so forcing it to fire would
    be testing the fixture rather than the engine.
    """
    import dataclasses

    from telegram_bot.db import utcnow
    from telegram_bot.engine import Signal
    from telegram_bot.orderflow import OrderFlowSnapshot
    from telegram_bot.scanner import Scanner
    from telegram_bot.tests.conftest import make_trending_frame

    permissive = dataclasses.replace(config, confidence_min=0.35)
    scanner = Scanner(db=db, config=permissive, market=market, started_at=0.0)

    now = utcnow()
    market.set_frame("XAUUSD", "5m", make_trending_frame(300, seconds=300))

    # A signal just fired, so the pair is inside its 30-minute cooldown.
    snapshot = OrderFlowSnapshot(
        "XAUUSD", "5m", 100.0, 200.0, "rising", None, 1.3, False, 1.0, "proxy", now
    )
    db.save_signal(
        Signal(
            symbol="XAUUSD",
            timeframe="5m",
            bar_ts=now,
            action="BUY",
            entry=100.0,
            sl=99.0,
            tp1=102.0,
            tp2=104.0,
            confidence=0.8,
            layers={"trend": 0.8},
            order_flow=snapshot,
            reason="test",
        ).to_record(sent_at=now)
    )

    # The automatic path is suppressed...
    result = await scanner.scan(symbol="XAUUSD", timeframe="5m", now=now)
    assert result.computed, "a signal should have been computed"
    assert result.delivered == []
    assert result.suppressed

    # ...but the manual command still answers.
    text = await cmd.handle_message(ctx, "/agenza-xauusd 5mn", user_id=1001)
    assert text is not None
    assert "Analysis" in text
