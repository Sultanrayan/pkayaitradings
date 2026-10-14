"""Bot wiring and entry point.

Two environment variables, neither ever logged:

* ``TELEGRAM_BOT_TOKEN`` — from @BotFather. **Required.**
* ``TELEGRAM_CHAT_ID`` — optional. When set, automatic alerts go only there. When
  unset, they are broadcast to everyone who has sent ``/start``.

Open to any user
----------------
The bot is not restricted to one chat. Anyone who messages it gets the full
command set, and ``/start`` registers them to receive automatic alerts. There is
no allow-list, no admin command, no setup token and no claim step (RULE 2).

Three consequences worth stating, because they are the reason this is safe to
open:

* **Commands are per-user.** Every reply goes back to whoever asked, and rate
  limits are keyed by ``user_id``, so one user exhausting their quota cannot deny
  the bot to anyone else.
* **Broadcasts are per-subscriber and fault-isolated.** One unreachable or deleted
  chat is logged and skipped; it does not stop delivery to the rest. A subscriber
  who blocks the bot simply stops appearing in the send log.
* **Nothing about a user is trusted.** ``user_id`` comes from Telegram, not from
  the message body, so no one can address alerts to a chat they do not belong to.
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from shared.logging import configure_logging, get_logger

_logger = get_logger(__name__)

__all__ = [
    "Bot",
    "BotSettings",
    "MissingCredentialsError",
    "build_bot",
    "main",
    "redact_token",
]

#: Default database location, relative to the repository root.
DEFAULT_DB_PATH = Path(__file__).resolve().parents[1] / "signals_bot.db"


class MissingCredentialsError(Exception):
    """Raised when a required environment variable is absent or empty.

    The message names the variable but never its value.
    """


@dataclass(frozen=True)
class BotSettings:
    """The bot's settings.

    Attributes:
        token: Telegram bot token. Never logged.
        chat_id: Optional single destination for automatic alerts. ``None`` means
            broadcast to every subscriber.
        db_path: SQLite file path.
    """

    token: str
    chat_id: int | None = None
    db_path: Path = DEFAULT_DB_PATH

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> BotSettings:
        """Read the token, and the chat id if one is configured.

        The token is required. ``TELEGRAM_CHAT_ID`` is not: with the bot open to
        any user there is no single correct chat, and requiring one would either
        invent an allow-list (RULE 2) or stop the bot starting at all.

        Args:
            env: Environment mapping. Defaults to ``os.environ``.

        Returns:
            The resolved settings.

        Raises:
MissingCredentialsError: When the token is absent or blank, or when a chat id
        is present but not an integer. A malformed chat id is an error rather than
        a silent fallback to broadcast, because a typo is far likelier than a
        deliberate omission.
        """
        source = env if env is not None else dict(os.environ)

        token = (source.get("TELEGRAM_BOT_TOKEN") or "").strip()
        if not token:
            raise MissingCredentialsError("TELEGRAM_BOT_TOKEN is not set")

        raw_chat = (source.get("TELEGRAM_CHAT_ID") or "").strip()
        chat_id: int | None = None
        if raw_chat:
            try:
                chat_id = int(raw_chat)
            except ValueError as exc:
                raise MissingCredentialsError(
                    "TELEGRAM_CHAT_ID must be an integer"
                ) from exc

        db_path = Path(source.get("SIGNALS_BOT_DB", str(DEFAULT_DB_PATH)))

        return BotSettings(token=token, chat_id=chat_id, db_path=db_path)


#: Shape of a Telegram bot token: numeric bot id, colon, then the secret. Used as
#: a fallback scrub so a token embedded in a request URL is caught even when the
#: environment variable is unset — which is exactly the case where an upstream
#: exception echoing that URL would otherwise reach the log store intact.
#:
#: No leading boundary: in ``/bot123456:AAAA...`` the character before the digits
#: is a word character, so ``\b`` would find no transition and the token in the
#: most common place to see one — a request URL — would go unscrubbed.
_TOKEN_PATTERN = re.compile(r"\d{5,}:[A-Za-z0-9_-]{20,}\b")


def redact_token(text: str, token: str | None = None) -> str:
    """Remove the bot token from a string.

    Applied to every log message and every Telegram reply that could contain a
    token — an upstream exception echoing a request URL is exactly how a
    credential reaches a log store.

    Two passes, because either one alone has a gap:

    1. An exact match on the configured token, which handles a token with an
       unexpected shape.
    2. A shape match on ``<digits>:<secret>``, which handles the common case of
       the environment not being populated in the process doing the logging.

    Args:
        text: The text to scrub.
        token: The token to remove. Read from the environment when omitted.

    Returns:
        The scrubbed text, with any token replaced by ``"<redacted>"``.
    """
    secret = token if token is not None else os.environ.get("TELEGRAM_BOT_TOKEN", "")
    scrubbed = text.replace(secret, "<redacted>") if secret else text
    return _TOKEN_PATTERN.sub("<redacted>", scrubbed)


@dataclass
class Bot:
    """Assembled bot, ready to run.

    Everything is constructed in :meth:`build` and exposed as attributes, so a test
    can substitute any part without the class reaching for globals.
    """

    settings: BotSettings
    db: Any
    config: Any
    market: Any
    scanner: Any
    scheduler: Any
    application: Any = None

    async def start(self) -> None:
        """Start polling and the scheduler, then block until cancelled."""
        _logger.info(
            "bot.starting",
            symbols=self.db.symbols(),
            timeframes=self.db.timeframes_for(self.db.symbols()[0]),
            db_path=str(self.settings.db_path),
        )
        await self.application.initialize()
        await self.application.start()
        self.scheduler.start()
        _logger.info("bot.started")
        try:
            await self.application.updater.start_polling(drop_pending_updates=True)
            await asyncio_sleep_forever()
        finally:
            self.scheduler.shutdown(wait=False)
            await self.application.updater.stop()
            await self.application.stop()
            await self.market.close()
            await self.application.shutdown()
            _logger.info("bot.stopped")

    async def broadcast(self, text: str) -> int:
        """Send one message to every alert destination. Returns how many got it.

        The token is scrubbed once, before fan-out, so it cannot reach a chat even
        if the message body were ever to contain it.

        Destinations are ``TELEGRAM_CHAT_ID`` when one is configured, and
        otherwise every active subscriber.

        A delivery failure is logged and skipped rather than raised. That is
        deliberate: a subscriber who has blocked the bot, or whose chat was
        deleted, must not be able to stop the alert reaching everyone else. The
        returned count is what actually landed.

        Args:
            text: Message body.

        Returns:
            Number of chats the message reached.
        """
        message = redact_token(text, self.settings.token)

        targets: list[int] = []
        if self.settings.chat_id is not None:
            targets.append(self.settings.chat_id)
        else:
            targets.extend(sub.chat_id for sub in self.db.subscribers())

        if not targets:
            _logger.info("broadcast.no_targets")
            return 0

        delivered = 0
        for chat_id in targets:
            try:
                await self.application.bot.send_message(chat_id=chat_id, text=message)
                delivered += 1
            except Exception as exc:
                # TelegramError and anything else. One bad chat must not end the
                # broadcast, and the reason is logged without the token.
                _logger.warning(
                    "broadcast.failed",
                    chat_id=chat_id,
                    error=redact_token(repr(exc), self.settings.token),
                )
        _logger.info("broadcast.done", delivered=delivered, attempted=len(targets))
        return delivered


async def asyncio_sleep_forever() -> None:
    """Block until cancelled."""
    import asyncio

    while True:
        await asyncio.sleep(3_600)


def build_bot(
    settings: BotSettings,
    *,
    application: Any = None,
    scheduler_factory: Any = None,
) -> Bot:
    """Construct every component and wire them together.

    Args:
        settings: Resolved credentials and database path.
        application: Optional pre-built Telegram ``Application``. Supplied by tests
            and by anything embedding the bot; built from the token when omitted.
        scheduler_factory: Optional override for the scheduler builder.

    Returns:
        An assembled :class:`Bot` with the polling started and handlers
        registered, but not yet running.

    Raises:
        ImportError: When ``python-telegram-bot`` is not installed.
    """
    from telegram.ext import MessageHandler, filters

    from telegram_bot.commands import (
        CommandContext,
        UnknownCommandError,
        handle_message,
        unknown_command_help,
    )
    from telegram_bot.db import Database
    from telegram_bot.defaults import BotConfig, seed_defaults
    from telegram_bot.market import MarketData
    from telegram_bot.scanner import Scanner
    from telegram_bot.scheduler import build_scheduler

    db = Database(settings.db_path)
    db.initialise()
    seed_defaults(db)
    config = BotConfig.load(db)

    market = MarketData()
    scanner = Scanner(db=db, config=config, market=market)
    cmd_ctx = CommandContext(db=db, config=config, scanner=scanner)

    async def deliver(result: Any) -> None:
        """Send a scan's signals. Injected into the scheduler, never the reverse."""
        from telegram_bot.formatter import format_confluence, format_signal

        for signal in result.delivered:
            await bot.broadcast(format_signal(signal))
        for confluence in result.confluences:
            cmd_ctx.confluence = confluence
            await bot.broadcast(format_confluence(confluence))

    async def summarise(weekly: bool) -> None:
        """Daily and weekly summary."""
        from telegram_bot.db import utcnow
        from telegram_bot.scheduler import summarise_performance

        stats = summarise_performance(scanner, days=7 if weekly else 1, now=utcnow())
        scope = "Weekly" if weekly else "Daily"
        await bot.broadcast(
            f"{scope} summary\n"
            + f"Signals: {stats['signals']}\n"
            + f"Resolved: {stats['resolved']}\n"
            + f"Win rate: {stats['win_rate']:.1f}%\n"
            + f"Avg RR: {stats['avg_rr']:.1f}\n"
            + f"Net move: {stats['total_pnl_pct']:+.2f}%\n"
        )

    factory = scheduler_factory or build_scheduler
    scheduler = factory(scanner=scanner, config=config, deliver=deliver, summarise=summarise)

    bot = Bot(
        settings=settings,
        db=db,
        config=config,
        market=market,
        scanner=scanner,
        scheduler=scheduler,
        application=application,
    )

    if bot.application is None:
        from telegram.ext import Application

        bot.application = Application.builder().token(settings.token).build()

    async def on_command(update: Any, ptb_context: Any) -> None:
        """Telegram entry point for every message.

        The second parameter is python-telegram-bot's own ``CallbackContext``. It
        is named ``ptb_context`` and deliberately unused: the bot's
        :class:`~telegram_bot.commands.CommandContext` is what the handlers need,
        and naming that one ``context`` shadowed it with PTB's object — every
        command then died on ``AttributeError: 'CallbackContext' object has no
        attribute 'db'`` and the user saw only "Something went wrong".

        Any user may use the bot; there is no allow-list and no authentication
        (RULE 2). Every reply goes back to the sender, and rate limits are keyed
        by their Telegram id, so one user's quota cannot be spent by another.

        ``/start`` additionally subscribes them to automatic alerts. That is the
        whole subscription mechanism: pressing /start, or coming back later,
        re-activates a registration rather than needing an admin to add them.
        """
        message = update.effective_message
        user = update.effective_user
        chat = update.effective_chat
        if message is None or user is None:
            return

        # Subscribe on /start. `user.id` and `chat.id` differ in a group, and
        # alerts must go to the conversation, not to the account's private chat.
        if chat is not None and (message.text or "").strip().split()[:1] == ["/start"]:
            db.subscribe(
                user.id,
                chat.id,
                username=user.username,
                first_name=user.first_name,
            )
            _logger.info(
                "subscriber.registered",
                user_id=user.id,
                chat_id=chat.id,
                total=db.subscriber_count(),
            )
        else:
            db.touch_subscriber(user.id)

        try:
            reply = await handle_message(cmd_ctx, message.text or "", user.id)
        except UnknownCommandError as exc:
            reply = unknown_command_help(db.symbols()) + f"\n\n{exc!s}"
        except ValueError as exc:
            reply = f"{exc}\n\nTry: {', '.join(db.timeframes_for(db.symbols()[0]))}"
        except Exception as exc:
            # A crash in one command must not kill polling, so this is caught
            # broadly and reported rather than propagated.
            _logger.exception("command.failed", error=redact_token(repr(exc), settings.token))
            reply = "Something went wrong. Try again shortly."
        if reply:
            await message.reply_text(redact_token(reply, settings.token))

    bot.application.add_handler(
        MessageHandler(filters.COMMAND, on_command)
    )
    return bot


def main() -> int:
    """Console entry point.

    Returns:
        Process exit code: 0 on clean shutdown, 2 when credentials are missing.
    """
    import asyncio

    configure_logging()
    try:
        settings = BotSettings.from_env()
    except MissingCredentialsError as exc:
        _logger.error("bot.credentials_missing", detail=str(exc))
        print(
            f"{exc}\n\nSet TELEGRAM_BOT_TOKEN, then start again. "
            "TELEGRAM_CHAT_ID is optional; without it alerts go to everyone who "
            "has sent /start.",
            file=sys.stderr,
        )
        return 2

    bot = build_bot(settings)
    try:
        asyncio.run(bot.start())
    except KeyboardInterrupt:  # pragma: no cover - interactive path
        _logger.info("bot.interrupted")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


def _token_pattern() -> re.Pattern[str]:
    """Pattern matching a Telegram bot token, for defence in depth."""
    return re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{30,}\b")


def scrub_secrets(text: str) -> str:
    """Remove anything token-shaped from a string.

    A backstop for :func:`redact_token`: if a token was rotated or supplied in an
    unexpected way, the pattern still catches it.

    Args:
        text: The text to scrub.

    Returns:
        The scrubbed text.
    """
    return _token_pattern().sub("<redacted>", text)
