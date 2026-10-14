"""Tests for the wiring in :func:`telegram_bot.app.build_bot`.

Every other test calls ``handle_message`` **directly** with the bot's own
``CommandContext``. That bypassed the one place the two contexts meet, and a
name collision there shipped a bug where **every command failed** with::

    AttributeError: 'CallbackContext' object has no attribute 'db'

python-telegram-bot passes its own ``CallbackContext`` as the second argument to
a handler. The handler had been written to accept that argument as ``context``
while also closing over a local named ``context``, so PTB's object shadowed the
bot's and the shadowed value was the one passed to ``handle_message``.

These tests drive the real registered handler with a stand-in ``CallbackContext``,
so that collision cannot come back unnoticed.
"""

from __future__ import annotations

from typing import Any

import pytest

from telegram_bot.app import BotSettings, build_bot

TOKEN = "123456:abcdefghijklmnopqrstuvwxyz0123456789"


class FakeMessage:
    """Stands in for ``update.effective_message``."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.replies: list[str] = []

    async def reply_text(self, text: str, **_kwargs: Any) -> None:
        self.replies.append(text)


class FakeUser:
    def __init__(self, user_id: int) -> None:
        self.id = user_id
        self.username = "tester"
        self.first_name = "Test"


class FakeChat:
    def __init__(self, chat_id: int) -> None:
        self.id = chat_id


class FakeUpdate:
    def __init__(self, text: str, user_id: int = 555, chat_id: int | None = None) -> None:
        self.effective_message = FakeMessage(text)
        self.effective_user = FakeUser(user_id)
        self.effective_chat = FakeChat(chat_id if chat_id is not None else user_id)


class FakeCallbackContext:
    """Deliberately has no ``db``.

    If the handler ever receives PTB's object instead of the bot's
    ``CommandContext``, the resulting ``AttributeError`` is what this reproduces.
    """


class FakeTelegramBot:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str, **_kwargs: Any) -> None:
        self.sent.append((chat_id, text))


class FakeApplication:
    """Captures the registered handler instead of talking to Telegram."""

    def __init__(self) -> None:
        self.bot = FakeTelegramBot()
        self.handlers: list[Any] = []

    def add_handler(self, handler: Any) -> None:
        self.handlers.append(handler)

    @property
    def handler(self) -> Any:
        assert self.handlers, "build_bot registered no handler"
        return self.handlers[-1].callback


@pytest.fixture
def wired(tmp_path, market):
    """A real ``build_bot`` wired to fakes, with the registered handler exposed.

    ``build_bot`` opens its own SQLite file at ``settings.db_path``, so the tests
    read ``bot.db`` rather than the shared ``db`` fixture — otherwise every
    assertion would inspect a different database than the bot is using.
    """
    application = FakeApplication()
    settings = BotSettings(token=TOKEN, db_path=tmp_path / "bot.db")
    bot = build_bot(settings, application=application)

    # build_bot constructs a real MarketData; swap in the stub for both the bot
    # and the scanner, which captured the original when it was constructed.
    bot.scanner.market = market

    yield bot, application

    bot.db.close()


async def _replies(wired, text: str, user_id: int = 555, chat_id: int | None = None) -> list[str]:
    """Invoke the registered handler exactly as PTB would, returning all replies.

    A command may legitimately produce zero replies — that is how a rate-limited
    call is meant to behave — so this does not assert on the count.
    """
    _bot, application = wired
    update = FakeUpdate(text, user_id=user_id, chat_id=chat_id)
    await application.handler(update, FakeCallbackContext())
    return update.effective_message.replies


async def _run(wired, text: str, user_id: int = 555, chat_id: int | None = None) -> str:
    """As :func:`_replies`, but requires that the user was answered."""
    replies = await _replies(wired, text, user_id=user_id, chat_id=chat_id)
    assert replies, f"{text!r} produced no reply at all"
    return replies[0]


# --------------------------------------------------------------------------- #
# The regression
# --------------------------------------------------------------------------- #


async def test_the_handler_receives_the_bots_own_context(wired) -> None:
    """Every command must reach ``handle_message`` with a usable context.

    Regression: PTB's ``CallbackContext`` shadowed the bot's, so this used to
    raise ``AttributeError: 'CallbackContext' object has no attribute 'db'`` and
    the user saw "Something went wrong. Try again shortly." for every command.
    """
    reply = await _run(wired, "/help")

    assert "Something went wrong" not in reply, "the handler crashed on its own context"
    assert "Powered by Pkay AI" in reply


@pytest.mark.parametrize(
    "command",
    ["/start", "/help", "/status", "/performance", "/confluence", "/orderflow"],
)
async def test_no_public_command_reports_an_internal_error(wired, command: str) -> None:
    """A crash in any command surfaces as this string; none may ever contain it."""
    reply = await _run(wired, command)
    assert "Something went wrong" not in reply, f"{command} crashed: {reply[:120]}"


async def test_an_unknown_command_still_gets_help(wired) -> None:
    reply = await _run(wired, "/nonsense")
    assert "Powered by Pkay AI" in reply


async def test_a_bad_agenza_argument_is_explained(wired) -> None:
    reply = await _run(wired, "/agenza-xauusd 30mn")
    assert "Unknown timeframe" in reply
    assert "Something went wrong" not in reply


# --------------------------------------------------------------------------- #
# Subscription happens through the real handler
# --------------------------------------------------------------------------- #


async def test_start_registers_the_sender_as_a_subscriber(wired) -> None:
    bot, _ = wired
    await _run(wired, "/start", user_id=777)
    assert bot.db.subscriber_count() == 1
    assert bot.db.subscribers()[0].user_id == 777


async def test_any_user_may_start_and_subscribe(wired) -> None:
    """No allow-list: the second user is registered the same as the first."""
    bot, _ = wired
    await _run(wired, "/start", user_id=111)
    await _run(wired, "/start", user_id=222)

    assert bot.db.subscriber_count() == 2
    assert {s.user_id for s in bot.db.subscribers()} == {111, 222}


async def test_a_group_start_records_the_chat_not_the_account(wired) -> None:
    """In a group the account id and the chat id differ; the chat is the target."""
    bot, _ = wired
    await _run(wired, "/start", user_id=333, chat_id=-100_888)

    sub = bot.db.subscribers()[0]
    assert sub.user_id == 333
    assert sub.chat_id == -100_888


async def test_another_command_does_not_subscribe(wired) -> None:
    """Only /start enrols someone. /status must not silently add a recipient."""
    bot, _ = wired
    await _run(wired, "/status", user_id=444)
    assert bot.db.subscriber_count() == 0


async def test_any_command_refreshes_last_seen(wired) -> None:
    bot, _ = wired
    await _run(wired, "/start", user_id=555)
    before = bot.db.subscribers()[0].last_seen
    await _run(wired, "/help", user_id=555)
    assert bot.db.subscribers()[0].last_seen >= before


async def test_one_users_rate_limit_does_not_block_another(wired) -> None:
    """Agenza is 1/min per user; exhausting one must not silence the other."""
    from telegram_bot.tests.conftest import make_frame

    bot, application = wired
    del application
    bot.scanner.market.set_frame("XAUUSD", "5m", make_frame(300))

    first = await _run(wired, "/agenza-xauusd 5mn", user_id=900)
    blocked = await _replies(wired, "/agenza-xauusd 5mn", user_id=900)
    other = await _run(wired, "/agenza-xauusd 5mn", user_id=901)

    assert "Something went wrong" not in first
    assert blocked == [], "a rate-limited call should say nothing at all"
    assert "Something went wrong" not in other


async def test_a_broadcast_reaches_only_registered_subscribers(wired) -> None:
    bot, _application = wired
    await _run(wired, "/start", user_id=1001)
    await _run(wired, "/start", user_id=1002)
    await _run(wired, "/status", user_id=1003)  # a user, but never started

    delivered = await bot.broadcast("BUY XAUUSD")

    assert delivered == 2
    assert {chat for chat, _ in _application.bot.sent} == {1001, 1002}


# --------------------------------------------------------------------------- #
# Delivery uses the subscriber list
# --------------------------------------------------------------------------- #


async def test_a_broadcast_reaches_a_registered_subscriber(wired) -> None:
    bot, application = wired
    await _run(wired, "/start", user_id=1001)

    delivered = await bot.broadcast("BUY XAUUSD")

    assert delivered == 1
    assert application.bot.sent[0][0] == 1001


async def test_a_reply_is_never_broadcast(wired) -> None:
    """A command answer goes only to the asker, never to every subscriber."""
    _bot, application = wired
    await _run(wired, "/start", user_id=1001)
    await _run(wired, "/start", user_id=1002)

    await _run(wired, "/status", user_id=1003)

    assert application.bot.sent == [], "a command reply leaked into the broadcast path"
