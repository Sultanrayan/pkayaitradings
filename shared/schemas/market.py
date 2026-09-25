"""Market-data schemas mirroring the biquote API payloads."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from shared.schemas.enums import Impact, MarketState

PositiveFloat = Annotated[float, Field(gt=0)]


class Tick(BaseModel):
    """A single biquote quote.

    biquote is a CFD broker feed: ``last`` and ``volume`` are always ``0`` and
    must not be used. Use :attr:`mid` (or ``bid``/``ask``) as the price.

    Attributes:
        symbol: Instrument ticker, e.g. ``XAUUSD``.
        bid: Best bid price.
        ask: Best ask price.
        mid: Midpoint of bid/ask — the canonical price.
        spread: ``ask - bid``.
        high: Session high.
        low: Session low.
        day_diff_percent: Percent change since the daily open.
        timestamp: ISO-8601 UTC tick timestamp.
        market_state: Whether the market is currently quoting.
        stale: Whether the quote is older than the freshness window.
        quote_age_seconds: Age of the quote in seconds.
    """

    model_config = ConfigDict(frozen=True)

    symbol: str
    description: str = ""
    bid: float
    ask: float
    mid: float
    spread: float = 0.0
    high: float | None = None
    low: float | None = None
    direction: str = "FLAT"
    day_diff_percent: float | None = Field(default=None, alias="dayDiffPercent")
    timestamp: datetime
    source: str = ""
    market_state: MarketState = Field(default=MarketState.UNKNOWN, alias="marketState")
    stale: bool = False
    quote_age_seconds: float = Field(default=0.0, alias="quoteAgeSeconds")
    last_quote_at: datetime | None = Field(default=None, alias="lastQuoteAt")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_tradeable(self) -> bool:
        """Whether the tick is fresh enough to act on."""
        return self.market_state is MarketState.OPEN and not self.stale


class OhlcBar(BaseModel):
    """A single OHLCV candlestick from ``/api/{symbol}/ohlc``.

    Bars from biquote arrive newest-first; the client reverses them so that
    consumers always see oldest-first. ``is_open`` marks the in-progress bar.
    """

    model_config = ConfigDict(frozen=True)

    open_time: datetime = Field(alias="openTime")
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    tick_volume: int = Field(default=0, alias="tickVolume")
    is_open: bool = Field(default=False, alias="isOpen")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def range(self) -> float:
        """Bar high minus low."""
        return self.high - self.low


class OhlcSeries(BaseModel):
    """An ordered (oldest-first) series of candles for one symbol/timeframe."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    interval: str
    bars: tuple[OhlcBar, ...] = ()

    @property
    def closed_bars(self) -> tuple[OhlcBar, ...]:
        """Only the completed bars, excluding the in-progress bar."""
        return tuple(bar for bar in self.bars if not bar.is_open)

    @property
    def latest_close(self) -> float | None:
        """Close of the most recent bar, if any."""
        return self.bars[-1].close if self.bars else None


class SymbolInfo(BaseModel):
    """Instrument metadata from ``/api/symbols``."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    name: str
    description: str = ""
    type: str = ""
    exchange: str = ""
    source: str = ""
    digits: int | None = None
    currency: str | None = None
    is_active: bool = Field(default=False, alias="isActive")
    has_data: bool = Field(default=False, alias="hasData")


class CalendarEvent(BaseModel):
    """A scheduled macroeconomic release from ``/api/calendar``.

    ``actual``/``forecast``/``previous`` are ``None`` when unpublished — ``None``
    means "no value", never zero. Compare ``actual`` against ``forecast``.
    """

    model_config = ConfigDict(frozen=True)

    id: str
    event_id: str = Field(alias="eventId")
    time: datetime
    period: datetime | None = None
    country_code: str = Field(alias="countryCode")
    currency: str | None = None
    name: str
    importance: Impact
    type: str = "event"
    sector: str | None = None
    unit: str | None = None
    multiplier: str | None = None
    digits: int | None = None
    actual: float | None = None
    forecast: float | None = None
    previous: float | None = None
    revised_previous: float | None = Field(default=None, alias="revisedPrevious")
    revision: float | None = None
    time_mode: str = Field(default="exact", alias="timeMode")
    source_url: str | None = Field(default=None, alias="sourceUrl")
    source: str = ""

    @field_validator("importance", mode="before")
    @classmethod
    def _upper_importance(cls, value: object) -> object:
        """biquote returns lowercase importance; normalise to the enum."""
        if isinstance(value, str):
            return value.upper()
        return value

    @property
    def surprise(self) -> float | None:
        """``actual - forecast`` when both are published, else ``None``."""
        if self.actual is None or self.forecast is None:
            return None
        return self.actual - self.forecast


class NewsArticle(BaseModel):
    """A news item from ``/api/news/market`` or ``/api/news/hn``."""

    model_config = ConfigDict(frozen=True)

    title: str
    description: str | None = None
    url: str
    publisher: str = ""
    published_date: datetime | None = Field(default=None, alias="publishedDate")
    image_url: str | None = Field(default=None, alias="imageUrl")
    category: str | None = None
    language: str | None = None
    country: str | None = None


class MarketMover(BaseModel):
    """A single entry from the gainers/losers/most-active feeds."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    symbol: str
    description: str = ""
    last_price: float = Field(alias="lastPrice")
    change_percent: float = Field(default=0.0, alias="changePercent")
    change_amount: float = Field(default=0.0, alias="changeAmount")
    volume: float = 0.0


class MarketSummary(BaseModel):
    """Aggregate market breadth from ``/api/market/summary``.

    The endpoint's shape is not fully documented, so unknown fields are kept.
    """

    model_config = ConfigDict(extra="allow")

    last_updated: datetime | None = Field(default=None, alias="lastUpdated")
