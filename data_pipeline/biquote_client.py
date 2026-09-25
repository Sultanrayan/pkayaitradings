"""Asynchronous REST client for the biquote market-data API.

biquote requires no API key and exposes free, real-time quotes for FX, metals,
crypto, index and equity CFDs. This client wraps the read endpoints with:

* typed Pydantic responses,
* transparent retries with exponential backoff + jitter,
* ``Retry-After`` handling on HTTP 429/503,
* a fixed-window rate limiter sized to the documented 15,000 req/min quota,
* the feed's documented gotchas (newest-first bars reversed, ``mid`` as price).

Example:
    >>> async with BiquoteClient() as client:
    ...     tick = await client.get_tick("XAUUSD")
    ...     series = await client.get_ohlc("XAUUSD", limit=200)
"""

from __future__ import annotations

import asyncio
import random
from datetime import datetime
from types import TracebackType
from typing import Any, Self

import httpx

from data_pipeline.errors import (
    BiquoteError,
    BiquoteNotFoundError,
    BiquoteRateLimitedError,
    BiquoteUnavailableError,
)
from data_pipeline.ohlc_store import OhlcStore
from shared.config import Settings, get_settings
from shared.logging import get_logger
from shared.schemas.enums import Impact, Timeframe
from shared.schemas.market import (
    CalendarEvent,
    MarketMover,
    MarketSummary,
    NewsArticle,
    OhlcBar,
    OhlcSeries,
    SymbolInfo,
    Tick,
)
from shared.utils.rate_limit import AsyncRateLimiter

_logger = get_logger(__name__)

_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


class BiquoteClient:
    """Async client for ``https://biquote.io/api``.

    Args:
        settings: Optional settings override; defaults to the cached app
            settings.
        client: Optional pre-built ``httpx.AsyncClient`` (useful for tests).
    """

    def __init__(
        self,
        settings: Settings | None = None,
        client: httpx.AsyncClient | None = None,
        *,
        ohlc_store: OhlcStore | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._base_url = self._settings.biquote_base_url.rstrip("/")
        self._max_retries = self._settings.biquote_max_retries
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(self._settings.biquote_timeout_seconds),
            headers={"Accept": "application/json", "User-Agent": "pkay-tdai/0.1"},
            follow_redirects=True,
        )
        self._limiter = AsyncRateLimiter(
            max_calls=self._settings.biquote_requests_per_minute,
            period_seconds=60.0,
        )
        # Accumulates candle history so chart consumers get a stable, growing
        # series instead of biquote's shallow, sliding intraday window.
        self._ohlc_store = ohlc_store or OhlcStore()

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.close()

    async def close(self) -> None:
        """Close the underlying HTTP client if this instance owns it."""
        if self._owns_client:
            await self._client.aclose()

    # ------------------------------------------------------------------ #
    # Core request plumbing
    # ------------------------------------------------------------------ #
    async def _request(
        self,
        path: str,
        *,
        params: Any = None,
    ) -> Any:
        """Perform a GET with retries, rate limiting and error mapping."""
        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            await self._limiter.acquire()
            try:
                response = await self._client.get(path, params=params)
            except httpx.TransportError as exc:  # timeouts, DNS, connection reset
                last_error = exc
                await self._sleep_backoff(attempt, reason=f"transport: {exc!r}")
                continue

            if response.status_code == 404:
                raise BiquoteNotFoundError(self._error_message(response, path))
            if response.status_code in _RETRYABLE_STATUS:
                retry_after = self._retry_after_seconds(response)
                last_error = BiquoteRateLimitedError(
                    self._error_message(response, path), retry_after=retry_after
                )
                if attempt < self._max_retries:
                    await self._sleep_backoff(
                        attempt,
                        reason=f"HTTP {response.status_code}",
                        override=retry_after,
                    )
                    continue
                break
            if response.is_error:
                raise BiquoteError(self._error_message(response, path))

            try:
                return response.json()
            except ValueError as exc:
                raise BiquoteError(f"Malformed JSON from {path}") from exc

        raise BiquoteUnavailableError(
            f"biquote request to {path} failed after {self._max_retries + 1} attempts: {last_error!r}"
        )

    async def _sleep_backoff(
        self,
        attempt: int,
        *,
        reason: str,
        override: float | None = None,
    ) -> None:
        delay = override if override is not None else min(2.0**attempt, 30.0)
        delay += random.uniform(0.0, 0.25 * max(delay, 1.0))
        _logger.warning(
            "biquote.retry",
            attempt=attempt + 1,
            reason=reason,
            delay_seconds=round(delay, 2),
        )
        await asyncio.sleep(delay)

    @staticmethod
    def _retry_after_seconds(response: httpx.Response) -> float:
        raw = response.headers.get("Retry-After")
        if raw:
            try:
                return max(float(raw), 0.0)
            except ValueError:
                return 60.0
        return 60.0

    @staticmethod
    def _error_message(response: httpx.Response, path: str) -> str:
        try:
            body = response.json()
        except ValueError:
            body = None
        if isinstance(body, dict):
            message = body.get("message") or body.get("error")
            if isinstance(message, str):
                return message
        return f"biquote request to {path} failed with HTTP {response.status_code}"

    # ------------------------------------------------------------------ #
    # Ticks
    # ------------------------------------------------------------------ #
    async def get_tick(self, symbol: str, *, allow_stale: bool = True) -> Tick:
        """Return the latest tick for one symbol.

        Args:
            symbol: Instrument ticker, e.g. ``XAUUSD``.
            allow_stale: When ``False``, raise :class:`BiquoteNotFound` if the
                quote is more than five minutes old.

        Returns:
            The parsed :class:`Tick`. A closed market returns the last known
            price with ``market_state == "closed"`` rather than raising.
        """
        payload = await self._request(
            f"/api/{symbol.upper()}",
            params={"allowStale": str(allow_stale).lower()},
        )
        return Tick.model_validate(payload)

    async def get_latest(self, symbols: list[str], *, allow_stale: bool = True) -> dict[str, Tick]:
        """Return the latest tick for many symbols in a single request.

        Symbols that have never quoted are omitted from the result.
        """
        if not symbols:
            return {}
        params: list[tuple[str, str]] = [("symbols", symbol.upper()) for symbol in symbols]
        params.append(("allowStale", str(allow_stale).lower()))
        payload = await self._request("/api/latest", params=params)
        if not isinstance(payload, dict):
            raise BiquoteError("Unexpected /api/latest response shape")
        return {name: Tick.model_validate(tick) for name, tick in payload.items()}

    async def get_tick_history(self, symbol: str, *, count: int = 100) -> list[Tick]:
        """Return raw tick history (newest-first) for a symbol."""
        if not 1 <= count <= 1000:
            raise ValueError("count must be between 1 and 1000")
        payload = await self._request(f"/api/{symbol.upper()}/history", params={"count": count})
        return [Tick.model_validate(item) for item in payload]

    # ------------------------------------------------------------------ #
    # Symbols
    # ------------------------------------------------------------------ #
    async def get_symbols(
        self,
        *,
        source: str | None = None,
        type_: str | None = None,
        exchange: str | None = None,
        active_only: bool = False,
        live_only: bool = False,
        quoted_within_days: int | None = None,
    ) -> list[SymbolInfo]:
        """Return the instrument catalogue with optional filters."""
        params: dict[str, Any] = {}
        if source:
            params["source"] = source
        if type_:
            params["type"] = type_
        if exchange:
            params["exchange"] = exchange
        if active_only:
            params["activeOnly"] = "true"
        if live_only:
            params["liveOnly"] = "true"
        if quoted_within_days is not None:
            if not 1 <= quoted_within_days <= 30:
                raise ValueError("quoted_within_days must be between 1 and 30")
            params["quotedWithinDays"] = quoted_within_days
        payload = await self._request("/api/symbols", params=params or None)
        return [SymbolInfo.model_validate(item) for item in payload]

    async def search_symbols(
        self,
        query: str,
        *,
        live_only: bool = False,
        limit: int = 25,
    ) -> list[SymbolInfo]:
        """Search symbols by name or description."""
        params: dict[str, Any] = {"q": query, "limit": limit}
        if live_only:
            params["liveOnly"] = "true"
        payload = await self._request("/api/symbols/search", params=params)
        return [SymbolInfo.model_validate(item) for item in payload]

    async def get_symbol(self, symbol: str) -> SymbolInfo:
        """Return metadata for a single symbol."""
        payload = await self._request(f"/api/symbols/{symbol.upper()}")
        return SymbolInfo.model_validate(payload)

    async def get_active_symbols(self) -> list[SymbolInfo]:
        """Return every symbol currently receiving ticks."""
        payload = await self._request("/api/active")
        return [SymbolInfo.model_validate(item) for item in payload]

    # ------------------------------------------------------------------ #
    # OHLC candles
    # ------------------------------------------------------------------ #
    async def get_ohlc(
        self,
        symbol: str,
        *,
        interval: Timeframe = Timeframe.H1,
        limit: int = 100,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> OhlcSeries:
        """Return OHLCV candles, normalised to oldest-first order.

        biquote returns bars newest-first and may include the in-progress bar;
        this method reverses them so consumers get a chronological series.
        """
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        params: dict[str, Any] = {"interval": interval.biquote_interval, "limit": limit}
        if start is not None:
            params["from"] = start.isoformat()
        if end is not None:
            params["to"] = end.isoformat()

        payload = await self._request(f"/api/{symbol.upper()}/ohlc", params=params)
        raw_bars = payload.get("bars", []) if isinstance(payload, dict) else payload
        bars = [OhlcBar.model_validate(bar) for bar in raw_bars]
        bars.reverse()

        symbol_name = str(payload.get("symbol", symbol.upper()))
        interval_name = str(payload.get("interval", interval.biquote_interval))

        # Historical range queries return exactly the requested slice, but are
        # still persisted so they enrich later "latest" requests.
        if start is not None or end is not None:
            self._ohlc_store.upsert(symbol_name, interval_name, bars)
            return OhlcSeries(symbol=symbol_name, interval=interval_name, bars=tuple(bars))

        # Streamed "latest" fetches merge into the local accumulator so the
        # chart gets a stable, growing window instead of biquote's shallow
        # history that slides on every request.
        merged = self._ohlc_store.merge(symbol_name, interval_name, bars, limit=limit)
        return OhlcSeries(symbol=symbol_name, interval=interval_name, bars=tuple(merged))

    # ------------------------------------------------------------------ #
    # Market statistics
    # ------------------------------------------------------------------ #
    async def get_market_movers(
        self,
        kind: str = "gainers",
        *,
        type_: str | None = None,
        exchange: str | None = None,
        limit: int = 10,
        period: str = "1D",
    ) -> list[MarketMover]:
        """Return gainers, losers or most-active symbols."""
        if kind not in {"gainers", "losers", "most-active"}:
            raise ValueError("kind must be gainers, losers or most-active")
        params: dict[str, Any] = {"limit": limit, "period": period}
        if type_:
            params["type"] = type_
        if exchange:
            params["exchange"] = exchange
        payload = await self._request(f"/api/market/{kind}", params=params)
        items = payload.get("items", []) if isinstance(payload, dict) else payload
        return [MarketMover.model_validate(item) for item in items]

    async def get_market_summary(self) -> MarketSummary:
        """Return overall market breadth."""
        payload = await self._request("/api/market/summary")
        return MarketSummary.model_validate(payload)

    # ------------------------------------------------------------------ #
    # News
    # ------------------------------------------------------------------ #
    async def get_news(
        self,
        *,
        symbol: str | None = None,
        language: str = "en",
        country: str = "US",
        max_results: int = 10,
    ) -> list[NewsArticle]:
        """Return aggregated market/finance news."""
        params: dict[str, Any] = {
            "language": language,
            "country": country,
            "maxResults": max_results,
        }
        if symbol:
            params["symbol"] = symbol.upper()
        payload = await self._request("/api/news/market", params=params)
        return [NewsArticle.model_validate(item) for item in payload]

    async def get_hacker_news(
        self, *, query: str | None = None, max_results: int = 10
    ) -> list[NewsArticle]:
        """Return Hacker News front-page stories or a keyword search."""
        params: dict[str, Any] = {"maxResults": max_results}
        if query:
            params["q"] = query
        payload = await self._request("/api/news/hn", params=params)
        return [NewsArticle.model_validate(item) for item in payload]

    # ------------------------------------------------------------------ #
    # Economic calendar
    # ------------------------------------------------------------------ #
    async def get_calendar(
        self,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        countries: list[str] | None = None,
        importance: Impact | None = None,
        event_type: str | None = None,
        limit: int = 200,
    ) -> list[CalendarEvent]:
        """Return scheduled releases in a date range, oldest-first."""
        params: dict[str, Any] = {"limit": limit}
        if start is not None:
            params["from"] = start.isoformat()
        if end is not None:
            params["to"] = end.isoformat()
        if countries:
            params["countries"] = ",".join(code.upper() for code in countries)
        if importance is not None:
            params["importance"] = importance.value.lower()
        if event_type:
            params["type"] = event_type
        payload = await self._request("/api/calendar", params=params)
        return [CalendarEvent.model_validate(item) for item in payload]

    async def get_upcoming_events(
        self,
        *,
        limit: int = 20,
        countries: list[str] | None = None,
        importance: Impact | None = None,
    ) -> list[CalendarEvent]:
        """Return the next scheduled releases over a 30-day horizon."""
        params: dict[str, Any] = {"limit": limit}
        if countries:
            params["countries"] = ",".join(code.upper() for code in countries)
        if importance is not None:
            params["importance"] = importance.value.lower()
        payload = await self._request("/api/calendar/upcoming", params=params)
        return [CalendarEvent.model_validate(item) for item in payload]

    async def get_calendar_countries(self) -> list[dict[str, str]]:
        """Return the country codes carried by the economic calendar."""
        payload = await self._request("/api/calendar/countries")
        return list(payload)

    async def get_event_history(self, event_id: str, *, limit: int = 24) -> list[CalendarEvent]:
        """Return past prints of one recurring calendar series, newest-first."""
        payload = await self._request(f"/api/calendar/{event_id}/history", params={"limit": limit})
        return [CalendarEvent.model_validate(item) for item in payload]

    # ------------------------------------------------------------------ #
    # Health
    # ------------------------------------------------------------------ #
    async def health(self) -> dict[str, Any]:
        """Return biquote feed/collector health."""
        payload = await self._request("/health")
        return dict(payload)
