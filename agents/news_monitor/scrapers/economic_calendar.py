"""Economic-calendar ingestion and symbol/currency mapping."""

from __future__ import annotations

from datetime import timedelta

from data_pipeline.biquote_client import BiquoteClient
from shared.schemas.enums import Impact
from shared.schemas.market import CalendarEvent
from shared.utils.time import utcnow

_METAL_AND_CRYPTO = ("XAU", "XAG", "XPT", "XPD", "BTC", "ETH", "XRP", "SOL", "BNB", "LTC", "BCH")


def quote_currency(symbol: str) -> str:
    """Return the fiat currency an instrument is quoted in.

    Gold, silver and the major crypto pairs on biquote are all quoted against
    the US dollar, so US macro releases are the relevant driver.

    Examples:
        >>> quote_currency("XAUUSD")
        'USD'
        >>> quote_currency("EURUSD")
        'USD'
        >>> quote_currency("USDJPY")
        'JPY'
    """
    upper = symbol.upper()
    if upper.startswith(_METAL_AND_CRYPTO):
        return "USD"
    if len(upper) == 6:
        return upper[3:]
    return "USD"


class EconomicCalendarSource:
    """Fetches and filters scheduled macro releases.

    Args:
        client: The shared biquote REST client.
    """

    def __init__(self, client: BiquoteClient) -> None:
        self._client = client

    async def upcoming(
        self,
        *,
        horizon_hours: int = 48,
        lookback_hours: int = 6,
        importance: Impact = Impact.HIGH,
        countries: list[str] | None = None,
    ) -> list[CalendarEvent]:
        """Return releases from ``now - lookback`` to ``now + horizon``.

        The short lookback captures figures published minutes ago, which matter
        as much as forthcoming ones.
        """
        now = utcnow()
        return await self._client.get_calendar(
            start=now - timedelta(hours=lookback_hours),
            end=now + timedelta(hours=horizon_hours),
            countries=countries,
            importance=importance,
            limit=200,
        )

    async def for_symbol(
        self,
        symbol: str,
        *,
        horizon_hours: int = 48,
        importance: Impact = Impact.HIGH,
    ) -> list[CalendarEvent]:
        """Return events in the instrument's quote currency."""
        currency = quote_currency(symbol)
        events = await self.upcoming(
            horizon_hours=horizon_hours, importance=importance, countries=None
        )
        return [event for event in events if event.currency == currency]
