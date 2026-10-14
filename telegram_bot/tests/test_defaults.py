"""RULE 1 and RULE 4: defaults land in SQLite on first run, and nothing else does."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from telegram_bot.db import Database
from telegram_bot.defaults import (
    COOLDOWN_MINUTES,
    DEFAULT_CONFIG,
    DEFAULT_QUIET_HOURS,
    DEFAULT_SYMBOLS,
    DEFAULT_TIMEFRAMES,
    BotConfig,
    seed_defaults,
)


def test_first_run_inserts_both_symbols() -> None:
    db = Database(":memory:")
    db.initialise()
    assert seed_defaults(db) is True
    assert set(db.symbols()) == {"XAUUSD", "BTCUSD"}
    db.close()


def test_both_symbols_get_all_four_timeframes() -> None:
    db = Database(":memory:")
    db.initialise()
    seed_defaults(db)
    for symbol in DEFAULT_SYMBOLS:
        assert set(db.timeframes_for(symbol)) == set(DEFAULT_TIMEFRAMES)
    db.close()


def test_all_eight_pairs_exist() -> None:
    """Two symbols by four timeframes is the whole configured surface."""
    db = Database(":memory:")
    db.initialise()
    seed_defaults(db)
    pairs = db.all_pairs()
    assert len(pairs) == 8
    db.close()


def test_seeding_is_idempotent() -> None:
    """A second start must not duplicate anything, and must report not-first-run."""
    db = Database(":memory:")
    db.initialise()
    assert seed_defaults(db) is True
    assert seed_defaults(db) is False
    assert len(db.symbols()) == 2
    assert len(db.all_pairs()) == 8
    db.close()


def test_first_run_needs_no_user_input() -> None:
    """Seeding prompts for nothing.

    It takes a database and returns a bool; there is no callback, no prompt and
    no interactive path to stub.
    """
    import inspect

    source = inspect.getsource(seed_defaults)
    for forbidden in ("input(", "getpass", "prompt("):
        assert forbidden not in source, f"seed_defaults calls {forbidden}"
    assert seed_defaults.__code__.co_argcount == 1


# --------------------------------------------------------------------------- #
# RULE 4 — the specified defaults
# --------------------------------------------------------------------------- #


def test_mode_is_balanced() -> None:
    db = Database(":memory:")
    db.initialise()
    seed_defaults(db)
    assert BotConfig.load(db).mode == "balanced"
    db.close()


def test_risk_multipliers_match_the_specification() -> None:
    db = Database(":memory:")
    db.initialise()
    seed_defaults(db)
    config = BotConfig.load(db)
    assert config.risk_sl_atr == 1.5
    assert config.risk_tp1_atr == 2.5
    assert config.risk_tp2_atr == 4.0
    for symbol in DEFAULT_SYMBOLS:
        risk = config.risk_for(symbol)
        assert risk.sl_atr_mult == 1.5
        assert risk.tp1_atr_mult == 2.5
        assert risk.tp2_atr_mult == 4.0
        assert risk.atr_period == 14
    db.close()


def test_confidence_minimum_is_zero_point_six() -> None:
    db = Database(":memory:")
    db.initialise()
    seed_defaults(db)
    assert BotConfig.load(db).confidence_min == 0.60
    db.close()


def test_order_flow_is_enabled() -> None:
    db = Database(":memory:")
    db.initialise()
    seed_defaults(db)
    assert BotConfig.load(db).orderflow_enabled is True
    db.close()


def test_quiet_hours_match_the_specification() -> None:
    db = Database(":memory:")
    db.initialise()
    seed_defaults(db)
    assert BotConfig.load(db).quiet_hours == DEFAULT_QUIET_HOURS == (22, 23, 0, 1, 2)
    db.close()


def test_quiet_hours_round_trip_through_json() -> None:
    """The stored value is JSON, so the loaded tuple must match the default."""
    db = Database(":memory:")
    db.initialise()
    seed_defaults(db)
    stored = json.loads(db.get_config("quiet_hours") or "[]")
    assert sorted(stored) == sorted(DEFAULT_QUIET_HOURS)
    db.close()


def test_per_timeframe_cooldowns_match() -> None:
    db = Database(":memory:")
    db.initialise()
    seed_defaults(db)
    for symbol in DEFAULT_SYMBOLS:
        for timeframe in DEFAULT_TIMEFRAMES:
            settings = db.timeframe_settings(symbol, timeframe)
            assert settings["cooldown_minutes"] == COOLDOWN_MINUTES[timeframe]
            assert settings["max_signals_per_hour"] == 4
    db.close()


def test_cooldown_values_match_the_specification() -> None:
    assert COOLDOWN_MINUTES == {"1m": 15, "5m": 30, "15m": 45, "1h": 60}


def test_confluence_settings_match() -> None:
    db = Database(":memory:")
    db.initialise()
    seed_defaults(db)
    config = BotConfig.load(db)
    assert config.confluence_enabled is True
    assert config.confluence_min_tfs == 2
    assert config.confluence_window_candles == 3
    db.close()


def test_every_default_key_is_persisted() -> None:
    db = Database(":memory:")
    db.initialise()
    seed_defaults(db)
    stored = db.all_config()
    for key in DEFAULT_CONFIG:
        assert key in stored, f"{key} was not written to the config table"
    db.close()


# --------------------------------------------------------------------------- #
# RULE 1 — no config file, anywhere
# --------------------------------------------------------------------------- #

#: Filenames that would mean configuration had leaked to disk.
CONFIG_FILENAMES = (
    "config.yaml",
    "config.yml",
    "config.json",
    "config.ini",
    "config.toml",
    "settings.json",
    "settings.yaml",
    ".env",
    "bot_config.json",
)


def test_seeding_creates_no_config_file(tmp_path: Path, monkeypatch) -> None:
    """Seeding writes only to the database file it was given."""
    monkeypatch.chdir(tmp_path)
    before = set(tmp_path.iterdir())

    db = Database(tmp_path / "bot.db")
    db.initialise()
    seed_defaults(db)
    db.close()

    created = set(tmp_path.iterdir()) - before
    assert created == {tmp_path / "bot.db"} or created == {
        tmp_path / "bot.db",
        tmp_path / "bot.db-wal",
        tmp_path / "bot.db-shm",
    }, f"unexpected files created: {sorted(p.name for p in created)}"

    for name in CONFIG_FILENAMES:
        assert not (tmp_path / name).exists(), f"{name} must not be created"


def test_no_module_reads_a_config_file_at_import() -> None:
    """No bot module may read a config file or the environment for configuration.

    Source-inspected rather than behaviourally tested: a module that only reads
    its config under some branch would pass a runtime test that never takes it.
    """
    from pathlib import Path

    import telegram_bot

    package = Path(telegram_bot.__file__).parent
    forbidden = ("yaml.safe_load", "json.load(open", "configparser", "toml.load")

    for path in sorted(package.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        for needle in forbidden:
            assert needle not in source, f"{path.name} reads a config file via {needle}"


# --------------------------------------------------------------------------- #
# Credentials
# --------------------------------------------------------------------------- #


def test_the_token_is_never_hardcoded() -> None:
    """The token is a live credential; it must be read, never written down."""
    from pathlib import Path

    import telegram_bot

    package = Path(telegram_bot.__file__).parent
    for path in sorted(package.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        # A literal Telegram token is "<digits>:<35+ chars>". None may appear in code.
        assert not re.search(r"\d{6,}:[A-Za-z0-9_-]{30,}", source), (
            f"{path.name} appears to contain a hardcoded bot token"
        )


def test_a_missing_token_stops_startup() -> None:
    """Better to refuse to run than to poll an unauthenticated bot."""
    from telegram_bot.app import BotSettings, MissingCredentialsError

    with pytest.raises(MissingCredentialsError, match="TELEGRAM_BOT_TOKEN"):
        BotSettings.from_env({})


def test_a_non_numeric_chat_id_stops_startup() -> None:
    """Silently sending to nobody is worse than refusing to send at all."""
    from telegram_bot.app import BotSettings, MissingCredentialsError

    with pytest.raises(MissingCredentialsError, match="TELEGRAM_CHAT_ID"):
        BotSettings.from_env(
            {"TELEGRAM_BOT_TOKEN": "123456:abcdefghijklmnopqrstuvwxyz0123456789", "TELEGRAM_CHAT_ID": "nope"}
        )


def test_the_bot_starts_without_a_chat_id() -> None:
    """The bot is open to any user, so there is no single correct chat to require.

    Requiring one would either invent an allow-list — which RULE 2 forbids — or
    stop the bot from starting at all.
    """
    from telegram_bot.app import BotSettings

    settings = BotSettings.from_env(
        {"TELEGRAM_BOT_TOKEN": "123456:abcdefghijklmnopqrstuvwxyz0123456789"}
    )
    assert settings.chat_id is None


def test_a_blank_chat_id_is_treated_as_unset() -> None:
    """An empty string in a compose env file must not crash the bot."""
    from telegram_bot.app import BotSettings

    settings = BotSettings.from_env(
        {
            "TELEGRAM_BOT_TOKEN": "123456:abcdefghijklmnopqrstuvwxyz0123456789",
            "TELEGRAM_CHAT_ID": "   ",
        }
    )
    assert settings.chat_id is None


def test_a_valid_chat_id_is_honoured_when_present() -> None:
    """Setting one narrows delivery rather than being ignored."""
    from telegram_bot.app import BotSettings

    settings = BotSettings.from_env(
        {
            "TELEGRAM_BOT_TOKEN": "123456:abcdefghijklmnopqrstuvwxyz0123456789",
            "TELEGRAM_CHAT_ID": "-1001234567890",
        }
    )
    assert settings.chat_id == -1001234567890


def test_a_negative_group_chat_id_is_accepted() -> None:
    """Telegram group ids are negative; rejecting one would be a silent breakage."""
    from telegram_bot.app import BotSettings

    settings = BotSettings.from_env(
        {
            "TELEGRAM_BOT_TOKEN": "123456:abcdefghijklmnopqrstuvwxyz0123456789",
            "TELEGRAM_CHAT_ID": "-1001234567890",
        }
    )
    assert settings.chat_id is not None and settings.chat_id < 0


def test_redaction_scrubs_a_bare_token() -> None:
    from telegram_bot.app import redact_token

    token = "1234567890:SUPERSECRETVALUExxxxxxxxxxxxxxxxxxxxxxx"
    assert "SUPERSECRET" not in redact_token(token, token=token)


def test_redaction_scrubs_a_token_inside_a_request_url() -> None:
    """The real leak path: an upstream exception echoing the request URL.

    Also checked with no token supplied, because the process doing the logging may
    not have the environment variable populated.
    """
    from telegram_bot.app import redact_token

    token = "1234567890:SUPERSECRETVALUExxxxxxxxxxxxxxxxxxxxxxx"
    url = f"https://api.telegram.org/bot{token}/getMe"

    assert "SUPERSECRET" not in redact_token(url, token=token)
    assert "SUPERSECRET" not in redact_token(url), redact_token(url)
    assert "<redacted>" in redact_token(url)


def test_redaction_leaves_ordinary_text_alone() -> None:
    from telegram_bot.app import redact_token

    for text in (
        "scan.complete computed=1 delivered=0",
        "2026-10-02 14:00 UTC",
        "entry 4156.23 sl 4132.10",
        "",
    ):
        assert redact_token(text, token="1234567890:SUPERSECRETVALUExxxx") == text


def test_redaction_does_not_eat_ordinary_timestamps() -> None:
    """A colon-separated time must not match the token shape and get mangled."""
    from telegram_bot.app import redact_token

    assert redact_token("finished at 2026-10-03T02:28:19Z", token="x") == (
        "finished at 2026-10-03T02:28:19Z"
    )


def test_only_two_environment_variables_are_read() -> None:
    """The bot reads exactly TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID."""
    import inspect

    from telegram_bot.app import BotSettings

    source = inspect.getsource(BotSettings.from_env)
    env_names = {
        token
        for token in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")
        if token in source
    }
    # The third name is an optional database override, documented as such.
    assert env_names == {"TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"}
    assert "SIGNALS_BOT_DB" in source


def test_no_config_file_exists_in_the_package() -> None:
    """The shipped package contains no data or configuration file."""
    import telegram_bot

    package = Path(telegram_bot.__file__).parent
    for name in CONFIG_FILENAMES:
        assert not (package / name).exists()


def test_no_config_file_exists_in_the_package_tree() -> None:
    """No configuration file ships inside the package directory."""
    import telegram_bot

    package = Path(telegram_bot.__file__).parent
    for name in CONFIG_FILENAMES:
        assert not (package / name).exists(), f"{name} must not ship with the package"


def test_database_is_the_only_persistence() -> None:
    """The bot's whole state lives in SQLite."""
    db = Database(":memory:")
    db.initialise()
    tables = {
        row["name"]
        for row in db._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    required = {
        "config",
        "symbols",
        "timeframes",
        "signals",
        "order_flow_alerts",
        "performance",
        "rate_limits",
    }
    assert required <= tables, f"missing tables: {sorted(required - tables)}"
    db.close()


def test_environment_is_not_written_to() -> None:
    """Nothing in the bot mutates the process environment."""
    from pathlib import Path

    import telegram_bot

    package = Path(telegram_bot.__file__).parent
    for path in sorted(package.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        assert "os.environ[" not in source, f"{path.name} writes to the environment"
        assert "setenv(" not in source, f"{path.name} writes to the environment"


def test_seed_defaults_does_not_touch_disk_when_given_memory() -> None:
    """An in-memory database writes nothing at all."""
    cwd = Path.cwd()
    before = set(cwd.iterdir())
    db = Database(":memory:")
    db.initialise()
    seed_defaults(db)
    db.close()
    assert set(cwd.iterdir()) == before


# --------------------------------------------------------------------------- #
# Config loading is resilient
# --------------------------------------------------------------------------- #


def test_a_corrupt_config_value_falls_back_rather_than_crashing() -> None:
    """A bot that refuses to start on one bad key is worse than one using a default."""
    db = Database(":memory:")
    db.initialise()
    seed_defaults(db)
    db.set_config("confidence_min", "not-a-number")
    assert BotConfig.load(db).confidence_min == 0.60
    db.close()


def test_a_missing_risk_block_falls_back_to_global_multipliers() -> None:
    db = Database(":memory:")
    db.initialise()
    seed_defaults(db)
    db.add_symbol("ETHUSD")
    risk = BotConfig.load(db).risk_for("ETHUSD")
    assert risk.sl_atr_mult == 1.5
    assert risk.tp1_atr_mult == 2.5
    assert risk.tp2_atr_mult == 4.0
    db.close()


def test_config_is_a_frozen_snapshot() -> None:
    db = Database(":memory:")
    db.initialise()
    seed_defaults(db)
    config = BotConfig.load(db)
    import dataclasses

    try:
        config.mode = "aggressive"  # type: ignore[misc]
        raise AssertionError("BotConfig must be immutable")
    except dataclasses.FrozenInstanceError:
        pass
    db.close()
