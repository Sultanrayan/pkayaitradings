"""Shared fixtures for the Telegram bot's tests.

Nothing here touches the network, Telegram, or a real database file. The market
data source is replaced with a deterministic stub, so every test runs offline and
produces the same result on every run.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd
import pytest

from telegram_bot.db import Database
from telegram_bot.defaults import BotConfig, seed_defaults

#: Fixed base timestamp so generated series are reproducible. 2026-10-02 00:00 UTC.
BASE_TS = 1_787_616_000


def make_frame(
    n: int = 300,
    *,
    start: float = 2_000.0,
    drift: float = 0.0005,
    noise: float = 0.0020,
    base_ts: int = BASE_TS,
    seconds: int = 300,
    tick_volume: bool = True,
    seed: int = 17,
) -> pd.DataFrame:
    """A seeded OHLCV frame indexed by bar close time in UTC.

    Args:
        n: Number of bars.
        start: First close.
        drift: Per-bar log drift.
        noise: Per-bar return noise.
        base_ts: Close time of the first bar, Unix seconds.
        seconds: Bar duration.
        tick_volume: Include a non-zero ``tick_volume`` column. When ``False`` the
            frame carries no volume at all, which is what a feed without volume
            looks like — the order-flow and volume layers must abstain.
        seed: RNG seed.

    Returns:
        Frame with ``open``/``high``/``low``/``close`` and optionally volume.
    """
    rng = np.random.default_rng(seed)
    closes = start * np.exp(np.cumsum(rng.normal(drift, noise, size=n)))
    opens = np.empty(n)
    opens[0] = start
    opens[1:] = closes[:-1]
    highs = np.maximum(opens, closes) * (1.0 + rng.uniform(0.0, 0.0015, size=n))
    lows = np.minimum(opens, closes) * (1.0 - rng.uniform(0.0, 0.0015, size=n))
    ticks = rng.integers(40, 200, size=n).astype(float)

    # `pd.Timestamp(int, tz=...)` interprets an int as NANOSECONDS, so passing
    # Unix seconds directly lands every bar in 1970. Build from the epoch second
    # explicitly and offset by whole bars.
    index = pd.DatetimeIndex(
        [
            pd.Timestamp(base_ts, unit="s", tz="UTC") + pd.Timedelta(seconds=seconds * i)
            for i in range(n)
        ],
        name="close_time",
    )
    data: dict[str, Any] = {
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
    }
    if tick_volume:
        data["tick_volume"] = ticks
    return pd.DataFrame(data, index=index)


#: A fixed moment in the middle of the active day — 14:00 UTC, deliberately far
#: from the configured quiet hours of [22, 23, 0, 1, 2].
#:
#: Delivery tests must pin their clock to this rather than call ``utcnow()``.
#: Quiet hours are real behaviour, so a test that lets the wall clock decide will
#: pass for 19 hours a day and fail for 5 — including every run between 22:00 and
#: 03:00 UTC, which is when this suite was first written.
ACTIVE_TS: int = int(
    datetime(2026, 10, 2, 14, 0, tzinfo=UTC).timestamp()
)

#: 23:30 UTC on the same day, inside the default quiet hours.
QUIET_TS: int = int(datetime(2026, 10, 2, 23, 30, tzinfo=UTC).timestamp())


class StubMarket:
    """In-memory :class:`~telegram_bot.market.MarketData` replacement.

    Returns a frame built by :func:`make_frame`, honours the ``tick_volume`` flag,
    and can be told to fail so the scanner's error paths are exercised.
    """

    def __init__(self, *, frames: dict[tuple[str, str], pd.DataFrame] | None = None) -> None:
        self._frames = frames or {}
        self.fail_for: set[tuple[str, str]] = set()
        self.calls: list[tuple[str, str]] = []

    def set_frame(self, symbol: str, timeframe: str, frame: pd.DataFrame) -> None:
        """Pin the frame returned for one pair."""
        self._frames[(symbol.upper(), timeframe)] = frame

    def fail(self, symbol: str, timeframe: str) -> None:
        """Make one pair raise, exercising the scanner's error handling."""
        self.fail_for.add((symbol.upper(), timeframe))

    async def closed_frame(self, symbol: str, timeframe: str) -> pd.DataFrame:
        """Return the pinned frame, or a default one."""
        from telegram_bot.market import BarsUnavailableError, DataError
        from telegram_bot.timeframes import TIMEFRAME_SECONDS

        key = (symbol.upper(), timeframe)
        self.calls.append(key)
        if key in self.fail_for:
            raise DataError(f"stub failure for {key[0]} {key[1]}")
        frame = self._frames.get(key)
        if frame is None:
            seconds = TIMEFRAME_SECONDS.get(timeframe, 300)
            frame = make_frame(300, seconds=seconds)
        if frame.empty:
            raise BarsUnavailableError(f"{key[0]} {key[1]} has no closed bars")
        return frame

    def cached_frame(self, symbol: str, timeframe: str) -> pd.DataFrame | None:
        """Return the pinned frame without any failure simulation."""
        return self._frames.get((symbol.upper(), timeframe))

    def invalidate(self, symbol: str | None = None) -> None:
        """No-op; the stub has no cache of its own."""
        return

    async def close(self) -> None:
        """No-op."""
        return


@pytest.fixture
def db() -> Database:
    """A seeded in-memory database with default config."""
    database = Database(":memory:")
    database.initialise()
    seed_defaults(database)
    yield database
    database.close()


@pytest.fixture
def config(db: Database) -> BotConfig:
    """Bot configuration loaded from the seeded database."""
    return BotConfig.load(db)


@pytest.fixture
def market() -> StubMarket:
    """A stub market with no frames pinned."""
    return StubMarket()


@pytest.fixture
def scanner(db: Database, config: BotConfig, market: StubMarket) -> Any:
    """A scanner wired to the stub market."""
    from telegram_bot.scanner import Scanner

    return Scanner(db=db, config=config, market=market, started_at=0.0)


@pytest.fixture
def ctx(db: Database, config: BotConfig, scanner: Any) -> Any:
    """A command context wired to the stub market."""
    from telegram_bot.commands import CommandContext

    return CommandContext(db=db, config=config, scanner=scanner)


def make_trending_frame(
    n: int = 300,
    *,
    up: bool = True,
    seconds: int = 300,
    slope: float = 0.0015,
    noise: float = 0.0004,
    seed: int = 5,
    end_ts: int | None = None,
) -> pd.DataFrame:
    """A frame whose layers agree, so a signal can actually fire.

    A seeded random walk will *not* produce a signal at the default 0.60
    threshold, and that is correct rather than a bug: on noise the layers
    genuinely disagree. Tests that need a signal need a market that agrees, so
    this builds one — a steady trend with rising volume and moderate noise.

    The slope is deliberately gentle. A steep trend pushes RSI to an extreme, and
    an overbought reading votes bearish against a bullish trend, which is correct
    mean-reversion behaviour and would defeat the point of the fixture.

    Args:
        n: Number of bars.
        up: ``True`` for a rally, ``False`` for a selloff.
        seconds: Bar duration.
        slope: Per-bar log drift.
        noise: Per-bar return noise.
        seed: RNG seed.
        end_ts: Unix seconds for the newest bar's close. Defaults to now. Pass
            :data:`ACTIVE_TS` when the caller also scans at a pinned clock, so
            the newest bar is closed relative to it rather than accidentally
            still forming.

    Returns:
        Frame indexed by bar close time, ending at the current bar.
    """
    rng = np.random.default_rng(seed)
    drift = abs(slope) * (1.0 if up else -1.0)
    closes = 2_000.0 * np.exp(np.cumsum(rng.normal(drift, noise, size=n)))
    opens = np.empty(n)
    opens[0] = closes[0]
    opens[1:] = closes[:-1]

    end_ts = int(time.time()) if end_ts is None else end_ts
    index = pd.DatetimeIndex(
        [pd.Timestamp(end_ts - seconds * (n - i), unit="s", tz="UTC") for i in range(n)],
        name="close_time",
    )
    return pd.DataFrame(
        {
            "open": opens,
            "high": closes * 1.0008,
            "low": opens * 0.9992,
            "close": closes,
            "tick_volume": np.linspace(60.0, 240.0, n),
        },
        index=index,
    )


@pytest.fixture
def trending_frame() -> pd.DataFrame:
    """A frame with a sustained rally, for direction-sensitive assertions."""
    return make_trending_frame(up=True)


@pytest.fixture
def falling_frame() -> pd.DataFrame:
    """A frame with a sustained selloff."""
    return make_trending_frame(up=False)


@pytest.fixture(autouse=True)
def _isolate_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep developer credentials out of the suite.

    The bot reads two credentials from the environment. Without this, a developer
    who has them exported would have every test run against their real bot.
    """
    from shared.config import get_settings

    for name in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "SIGNALS_BOT_DB"):
        monkeypatch.delenv(name, raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
