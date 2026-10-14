"""Market data access for the bot.

Thin wrapper over the project's existing biquote client, adding the two things
the bot needs and the client does not expose: a per-timeframe cache (the scanner
touches the same symbol on four timeframes every minute) and a hard rule that
only closed bars leave this module.

The in-progress bar is dropped **here**, at the source, before any frame reaches
the engine. The engine has its own closure gate as a second line of defence, but
the cheapest place to enforce a rule is where the untrusted data enters.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import pandas as pd

from data_pipeline.biquote_client import BiquoteClient
from shared.config import get_settings
from shared.schemas.enums import Timeframe
from shared.schemas.market import OhlcSeries
from telegram_bot.engine import to_closed_frame
from telegram_bot.timeframes import TIMEFRAME_SECONDS

__all__ = ["BarsUnavailableError", "DataError", "MarketData"]

#: Bars requested per fetch. Comfortably above the engine's EMA-200 warmup.
DEFAULT_LOOKBACK = 400

#: Internal bot timeframe -> the shared :class:`~shared.schemas.enums.Timeframe`
#: member that knows how to spell it for biquote.
#:
#: Two vocabularies meet here. The bot says ``5m``; the shared enum's members are
#: named ``M5`` and carry the *value* ``"M5"``, with the biquote string ``"5m"``
#: reached through its ``biquote_interval`` property. Mapping internal names
#: straight onto enum values therefore fails: ``Timeframe("5m")`` raises
#: ``ValueError``, which surfaced as every fetch erroring out.
#:
#: The biquote spelling is deliberately not repeated here. It is derived from the
#: enum so the two cannot drift apart.
_INTERNAL_TO_ENUM: dict[str, Timeframe] = {
    "1m": Timeframe.M1,
    "5m": Timeframe.M5,
    "15m": Timeframe.M15,
    "1h": Timeframe.H1,
}


class DataError(Exception):
    """Raised when market data cannot be obtained or is unusable."""


class BarsUnavailableError(DataError):
    """Raised when a symbol/timeframe has no closed bars to evaluate."""


@dataclass
class MarketData:
    """Cached accessor for closed-bar frames.

    Deliberately **not** frozen. It owns a frame cache and an ``asyncio.Lock`` and
    fills both in ``__post_init__``; ``frozen=True`` made every instantiation
    raise ``FrozenInstanceError``, so the bot could not start at all. The tests
    missed it because they all substituted a stub market and nothing ever
    constructed this class.

    Args:
        client: Optional biquote client. When supplied the caller owns its
            lifetime and must close it; otherwise this object creates and closes
            its own.
        lookback: Bars requested per fetch.

    Example:
        >>> async def scan():                     # doctest: +SKIP
        ...     async with MarketData() as data:
        ...         frame = await data.closed_frame("XAUUSD", "5m")
    """

    client: BiquoteClient | None = None
    lookback: int = DEFAULT_LOOKBACK

    def __post_init__(self) -> None:
        self._owns_client = self.client is None
        self._client = self.client or BiquoteClient(get_settings())
        self._cache: dict[tuple[str, str], pd.DataFrame] = {}
        self._lock = asyncio.Lock()

    async def close(self) -> None:
        """Release the client when this object owns it."""
        if self._owns_client:
            await self._client.close()

    async def __aenter__(self) -> MarketData:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.close()

    async def series(self, symbol: str, timeframe: str) -> OhlcSeries:
        """Fetch the raw feed series for one pair.

        Raises:
            DataError: When the pair is not a known timeframe or the fetch fails.
        """
        enum = _INTERNAL_TO_ENUM.get(timeframe)
        if enum is None:
            raise DataError(f"unsupported timeframe: {timeframe!r}")

        try:
            return await self._client.get_ohlc(
                symbol.upper(), interval=enum, limit=self.lookback
            )
        except Exception as exc:
            raise DataError(f"{symbol.upper()} {timeframe} fetch failed: {exc!r}") from exc

    async def closed_frame(self, symbol: str, timeframe: str) -> pd.DataFrame:
        """Fetch and cache the closed-bar frame for one pair.

        The in-progress bar is dropped here. Nothing downstream ever sees it.

        Raises:
            BarsUnavailableError: When the pair has no closed bars.
            DataError: When the fetch fails.
        """
        key = (symbol.upper(), timeframe)
        async with self._lock:
            cached = self._cache.get(key)
            # A cached frame is reused only while its newest bar is still the
            # newest. Once time has advanced past a further bar's close, serving
            # the cache would present a stale bar as the current one.
            if cached is not None and len(cached) and cached.index[-1] >= _current_close(timeframe):
                return cached

        series = await self.series(symbol, timeframe)
        frame = to_closed_frame(series, timeframe)
        if frame.empty:
            raise BarsUnavailableError(f"{symbol.upper()} {timeframe} has no closed bars")

        async with self._lock:
            self._cache[key] = frame
        return frame

    def cached_frame(self, symbol: str, timeframe: str) -> pd.DataFrame | None:
        """Return a cached frame without fetching. Used by ``/orderflow``."""
        return self._cache.get((symbol.upper(), timeframe))

    def invalidate(self, symbol: str | None = None) -> None:
        """Drop cached frames for one symbol, or all of them."""
        if symbol is None:
            self._cache.clear()
            return
        prefix = symbol.upper()
        for key in [k for k in self._cache if k[0] == prefix]:
            del self._cache[key]


def _current_close(timeframe: str) -> pd.Timestamp:
    """Close time of the bar currently forming, in UTC."""
    import time

    now = int(time.time())
    seconds = TIMEFRAME_SECONDS[timeframe]
    return pd.Timestamp(now - (now % seconds), tz="UTC") + pd.Timedelta(seconds=seconds)


def describe_frame(frame: pd.DataFrame) -> dict[str, Any]:
    """Summarise a frame for logging, without dumping its contents."""
    if frame is None or frame.empty:
        return {"bars": 0}
    return {
        "bars": len(frame),
        "newest_close": frame.index[-1].isoformat(),
        "oldest_close": frame.index[0].isoformat(),
    }
