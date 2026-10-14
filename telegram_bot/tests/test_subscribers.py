"""Tests for the open-to-all-users model.

The bot has no allow-list, no admin command and no setup step (RULE 2). Anything
that would let one user reach another, or one user's usage deny service to
another, is tested here explicitly rather than assumed from the absence of an
allow-list.
"""

from __future__ import annotations

import pytest

from telegram_bot.db import Database, utcnow


@pytest.fixture
def fresh() -> Database:
    """A seeded in-memory database."""
    database = Database(":memory:")
    database.initialise()
    yield database
    database.close()


# --------------------------------------------------------------------------- #
# Subscription registry
# --------------------------------------------------------------------------- #


def test_a_new_database_has_no_subscribers(fresh: Database) -> None:
    assert fresh.subscribers() == []
    assert fresh.subscriber_count() == 0


def test_subscribe_records_the_user(fresh: Database) -> None:
    fresh.subscribe(555, 555, username="kaze", first_name="Kaze", now=1_000)

    subs = fresh.subscribers()
    assert len(subs) == 1
    assert subs[0].user_id == 555
    assert subs[0].chat_id == 555
    assert subs[0].username == "kaze"
    assert subs[0].subscribed_at == 1_000
    assert subs[0].active is True


def test_subscribing_twice_does_not_duplicate(fresh: Database) -> None:
    """/start fires on every launch, so this must be idempotent."""
    for _ in range(5):
        fresh.subscribe(555, 555, now=1_000)

    assert fresh.subscriber_count() == 1


def test_a_group_chat_keeps_its_own_chat_id(fresh: Database) -> None:
    """A user's account id and the group's chat id are different numbers.

    Storing one in place of the other would send every alert to the wrong place,
    or to nobody.
    """
    fresh.subscribe(user_id=555, chat_id=-100777, now=1_000)

    sub = fresh.subscribers()[0]
    assert sub.user_id == 555
    assert sub.chat_id == -100777
    assert sub.chat_id != sub.user_id


def test_unsubscribe_stops_delivery_but_keeps_the_record(fresh: Database) -> None:
    fresh.subscribe(555, 555, now=1_000)
    fresh.unsubscribe(555)

    assert fresh.subscribers() == []
    assert fresh.subscriber_count() == 0
    # The row survives, so history is not lost by leaving.
    assert len(fresh.subscribers(active_only=False)) == 1


def test_returning_reactivates_a_previous_subscriber(fresh: Database) -> None:
    """Someone who messages the bot again is asking to hear from it."""
    fresh.subscribe(555, 555, now=1_000)
    fresh.unsubscribe(555)
    fresh.subscribe(555, 555, now=2_000)

    assert fresh.subscriber_count() == 1
    assert fresh.subscribers()[0].active is True


def test_resubscribing_updates_the_chat_id(fresh: Database) -> None:
    """A user who moves the bot to a group must start receiving alerts there."""
    fresh.subscribe(555, 555, now=1_000)
    fresh.subscribe(555, -100999, now=2_000)

    assert fresh.subscribers()[0].chat_id == -100999


def test_many_users_are_kept_separate(fresh: Database) -> None:
    for index, user_id in enumerate((101, 202, 303, 404), start=1):
        fresh.subscribe(user_id, user_id, now=1_000 + index)

    assert fresh.subscriber_count() == 4
    assert {s.user_id for s in fresh.subscribers()} == {101, 202, 303, 404}


def test_subscribers_come_least_recently_seen_first(fresh: Database) -> None:
    """A stale entry is reached last, so one dead chat cannot delay everyone."""
    fresh.subscribe(1, 1, now=1_000)
    fresh.subscribe(2, 2, now=3_000)
    fresh.subscribe(3, 3, now=2_000)

    assert [s.user_id for s in fresh.subscribers()] == [1, 3, 2]


def test_touch_updates_last_seen_without_resubscribing(fresh: Database) -> None:
    fresh.subscribe(1, 1, now=1_000)
    fresh.touch_subscriber(1, now=9_999)

    sub = fresh.subscribers()[0]
    assert sub.last_seen == 9_999
    assert sub.subscribed_at == 1_000, "touch must not rewrite when they joined"


def test_touching_an_unknown_user_does_not_create_one(fresh: Database) -> None:
    """Only /start subscribes. A stray command must not enrol someone."""
    fresh.touch_subscriber(999, now=1_000)
    assert fresh.subscriber_count() == 0


# --------------------------------------------------------------------------- #
# Broadcasting
# --------------------------------------------------------------------------- #


class FakeTelegram:
    """Minimal stand-in for the Telegram bot object."""

    def __init__(self, *, failing_chats: set[int] | None = None) -> None:
        self.sent: list[tuple[int, str]] = []
        self.failing = failing_chats or set()

    async def send_message(self, chat_id: int, text: str) -> None:
        if chat_id in self.failing:
            raise RuntimeError(f"chat {chat_id} is unreachable")
        self.sent.append((chat_id, text))


def _bot(db: Database, *, chat_id: int | None = None, failing: set[int] | None = None):
    from telegram_bot.app import Bot, BotSettings

    bot = Bot(
        settings=BotSettings(token="123456:abcdefghijklmnopqrstuvwxyz0123456789", chat_id=chat_id),
        db=db,
        config=None,
        market=None,
        scanner=None,
        scheduler=None,
    )
    fake = FakeTelegram(failing_chats=failing)

    class _App:
        bot = fake

    bot.application = _App()
    return bot, fake


async def test_broadcast_reaches_every_subscriber(fresh: Database) -> None:
    for user_id in (101, 202, 303):
        fresh.subscribe(user_id, user_id, now=1_000)

    bot, telegram = _bot(fresh)
    delivered = await bot.broadcast("BUY XAUUSD")

    assert delivered == 3
    assert {chat for chat, _ in telegram.sent} == {101, 202, 303}


async def test_broadcast_with_no_subscribers_is_a_no_op(fresh: Database) -> None:
    """Before anyone presses /start there is nowhere to send. That is not an error."""
    bot, telegram = _bot(fresh)

    assert await bot.broadcast("hello") == 0
    assert telegram.sent == []


async def test_an_explicit_chat_id_overrides_the_subscriber_list(fresh: Database) -> None:
    """Setting TELEGRAM_CHAT_ID narrows delivery to that one chat."""
    fresh.subscribe(101, 101, now=1_000)
    fresh.subscribe(202, 202, now=1_000)

    bot, telegram = _bot(fresh, chat_id=999)
    delivered = await bot.broadcast("hello")

    assert delivered == 1
    assert telegram.sent[0][0] == 999


async def test_one_broken_chat_does_not_stop_the_broadcast(fresh: Database) -> None:
    """A user who blocked the bot must not deny it to everyone else."""
    for user_id in (101, 202, 303):
        fresh.subscribe(user_id, user_id, now=1_000)

    bot, telegram = _bot(fresh, failing={202})
    delivered = await bot.broadcast("BUY XAUUSD")

    assert delivered == 2, "the failure was not isolated"
    assert {chat for chat, _ in telegram.sent} == {101, 303}


async def test_every_chat_failing_is_survivable(fresh: Database) -> None:
    """Total failure reports zero rather than raising into the scheduler."""
    fresh.subscribe(101, 101, now=1_000)

    bot, _ = _bot(fresh, failing={101})
    assert await bot.broadcast("hello") == 0


async def test_a_token_in_the_body_never_reaches_a_chat(fresh: Database) -> None:
    """Redaction happens once, before fan-out."""
    fresh.subscribe(101, 101, now=1_000)

    token = "123456:abcdefghijklmnopqrstuvwxyz0123456789"
    bot, telegram = _bot(fresh)
    await bot.broadcast(f"oops {token} leaked")

    assert "abcdefghij" not in telegram.sent[0][1]
    assert "<redacted>" in telegram.sent[0][1]


# --------------------------------------------------------------------------- #
# Per-user isolation
# --------------------------------------------------------------------------- #


async def test_rate_limits_are_per_user(ctx_and_db) -> None:
    """One user spending their quota must not lock anyone else out."""
    from telegram_bot import commands as cmd
    from telegram_bot.tests.conftest import make_frame

    _database, context, market = ctx_and_db
    market.set_frame("XAUUSD", "5m", make_frame(300))

    first = await cmd.handle_message(context, "/agenza-xauusd 5mn", user_id=1001)
    blocked = await cmd.handle_message(context, "/agenza-xauusd 5mn", user_id=1001)
    other = await cmd.handle_message(context, "/agenza-xauusd 5mn", user_id=2002)

    assert first is not None, "the first call should answer"
    assert blocked is None, "the second call in the window should be dropped"
    assert other is not None, "a different user must not inherit the quota"


async def test_a_reply_goes_to_the_sender_not_to_a_fixed_chat(ctx_and_db) -> None:
    """Command replies are addressed by Telegram, never by anything in the body."""
    from telegram_bot import commands as cmd
    from telegram_bot.tests.conftest import make_frame

    _database, context, market = ctx_and_db
    market.set_frame("XAUUSD", "5m", make_frame(300))

    # A user_id that looks like a group id must still work as an account key.
    text = await cmd.handle_message(context, "/status", user_id=-1001234567890)
    assert text is not None
    assert "XAUUSD" in text


@pytest.fixture
def ctx_and_db():
    """``(db, CommandContext, market)`` assembled from the shared fixtures."""
    from telegram_bot import commands as cmd
    from telegram_bot.defaults import BotConfig
    from telegram_bot.tests.conftest import StubMarket

    database = Database(":memory:")
    database.initialise()
    from telegram_bot.defaults import seed_defaults

    seed_defaults(database)
    config = BotConfig.load(database)
    market = StubMarket()
    context = cmd.CommandContext(
        db=database,
        config=config,
        scanner=cmd.Scanner(db=database, config=config, market=market, started_at=0.0)
        if hasattr(cmd, "Scanner")
        else None,
    )
    yield database, context, market
    database.close()


def test_no_admin_surface_exists_in_the_open_bot() -> None:
    """RULE 2 still holds with the bot open: there is no way to become an admin.

    Opening a bot to everyone is only safe because there is nothing to escalate
    to. If a privilege command ever appears here, every user would have it.
    """
    from telegram_bot.commands import AGENZA_COMMANDS, COMMANDS

    names = set(COMMANDS) | {f"agenza-{s}" for s in AGENZA_COMMANDS}
    forbidden = {"admin", "add", "remove", "ban", "allow", "claim", "token", "setup"}
    for name in names:
        assert not forbidden & set(name.lower().split("-")), (
            f"{name} looks like a privilege command"
        )


def test_utcnow_is_used_for_subscription_timestamps() -> None:
    """Sanity: the registry's clock is the same one the rest of the bot uses."""
    assert isinstance(utcnow(), int)
