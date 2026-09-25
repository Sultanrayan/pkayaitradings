"""Additional biquote REST client tests covering the remaining endpoints."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
import respx

from data_pipeline.biquote_client import BiquoteClient
from data_pipeline.errors import (
    BiquoteError,
    BiquoteNotFoundError,
    BiquoteUnavailableError,
)
from shared.config import Settings
from shared.schemas.enums import Impact, Timeframe

BASE = "https://biquote.io"

TICK = {
    "symbol": "XAUUSD",
    "bid": 1.0,
    "ask": 1.2,
    "mid": 1.1,
    "spread": 0.2,
    "timestamp": "2026-02-24T10:30:00Z",
    "marketState": "open",
}

SYMBOL = {
    "name": "XAUUSD",
    "description": "Gold",
    "type": "Commodity",
    "exchange": "Forex",
    "source": "MT5",
    "isActive": True,
    "hasData": True,
}

EVENT = {
    "id": "mql5:1",
    "eventId": "mql5:840",
    "time": "2026-08-07T12:30:00Z",
    "countryCode": "US",
    "currency": "USD",
    "name": "Nonfarm Payrolls",
    "importance": "high",
    "type": "indicator",
    "actual": 152000,
    "forecast": 145000,
}

ARTICLE = {
    "title": "Gold rallies",
    "description": "desc",
    "url": "https://example.com/a",
    "publisher": "Reuters",
    "publishedDate": "2026-02-24T09:15:00Z",
}


@respx.mock
async def test_tick_history(settings: Settings) -> None:
    respx.get(f"{BASE}/api/XAUUSD/history").mock(
        return_value=httpx.Response(200, json=[TICK, TICK])
    )
    async with BiquoteClient(settings) as client:
        ticks = await client.get_tick_history("XAUUSD", count=2)
    assert len(ticks) == 2


@respx.mock
async def test_symbols_endpoints(settings: Settings) -> None:
    respx.get(f"{BASE}/api/symbols").mock(return_value=httpx.Response(200, json=[SYMBOL]))
    respx.get(f"{BASE}/api/symbols/search").mock(return_value=httpx.Response(200, json=[SYMBOL]))
    respx.get(f"{BASE}/api/symbols/XAUUSD").mock(return_value=httpx.Response(200, json=SYMBOL))
    respx.get(f"{BASE}/api/active").mock(return_value=httpx.Response(200, json=[SYMBOL]))
    async with BiquoteClient(settings) as client:
        symbols = await client.get_symbols(
            source="MT5", type_="Commodity", exchange="Forex", live_only=True, quoted_within_days=7
        )
        found = await client.search_symbols("gold", limit=5)
        one = await client.get_symbol("XAUUSD")
        active = await client.get_active_symbols()
    assert symbols[0].has_data is True
    assert found[0].name == "XAUUSD"
    assert one.name == "XAUUSD"
    assert active[0].is_active is True


@respx.mock
async def test_symbols_validation(settings: Settings) -> None:
    async with BiquoteClient(settings) as client:
        with pytest.raises(ValueError):
            await client.get_symbols(quoted_within_days=99)


@respx.mock
async def test_market_endpoints(settings: Settings) -> None:
    movers = {
        "period": "1D",
        "items": [
            {"symbol": "XAUUSD", "description": "Gold", "lastPrice": 1.0, "changePercent": 4.2}
        ],
    }
    respx.get(f"{BASE}/api/market/gainers").mock(return_value=httpx.Response(200, json=movers))
    respx.get(f"{BASE}/api/market/summary").mock(
        return_value=httpx.Response(200, json={"lastUpdated": "2026-02-24T10:00:00Z"})
    )
    async with BiquoteClient(settings) as client:
        gainers = await client.get_market_movers("gainers", type_="Commodity", limit=5)
        summary = await client.get_market_summary()
        with pytest.raises(ValueError):
            await client.get_market_movers("bogus")
    assert gainers[0].change_percent == 4.2
    assert summary.last_updated is not None


@respx.mock
async def test_news_endpoints(settings: Settings) -> None:
    respx.get(f"{BASE}/api/news/market").mock(return_value=httpx.Response(200, json=[ARTICLE]))
    respx.get(f"{BASE}/api/news/hn").mock(return_value=httpx.Response(200, json=[ARTICLE]))
    async with BiquoteClient(settings) as client:
        market = await client.get_news(symbol="XAUUSD")
        hn = await client.get_hacker_news(query="gold")
    assert market[0].publisher == "Reuters"
    assert hn[0].title == "Gold rallies"


@respx.mock
async def test_calendar_endpoints(settings: Settings) -> None:
    respx.get(f"{BASE}/api/calendar").mock(return_value=httpx.Response(200, json=[EVENT]))
    respx.get(f"{BASE}/api/calendar/upcoming").mock(return_value=httpx.Response(200, json=[EVENT]))
    respx.get(f"{BASE}/api/calendar/countries").mock(
        return_value=httpx.Response(200, json=[{"code": "US", "name": "US", "currency": "USD"}])
    )
    respx.get(f"{BASE}/api/calendar/mql5:840/history").mock(
        return_value=httpx.Response(200, json=[EVENT])
    )
    async with BiquoteClient(settings) as client:
        events = await client.get_calendar(
            start=datetime(2026, 8, 1, tzinfo=UTC),
            end=datetime(2026, 8, 8, tzinfo=UTC),
            countries=["us"],
            importance=Impact.HIGH,
            event_type="indicator",
        )
        upcoming = await client.get_upcoming_events(countries=["US"], importance=Impact.HIGH)
        countries = await client.get_calendar_countries()
        history = await client.get_event_history("mql5:840")
    assert events[0].importance is Impact.HIGH
    assert events[0].surprise == pytest.approx(7000.0)
    assert upcoming[0].event_id == "mql5:840"
    assert countries[0]["code"] == "US"
    assert history[0].actual == 152000


@respx.mock
async def test_health_endpoint(settings: Settings) -> None:
    respx.get(f"{BASE}/health").mock(return_value=httpx.Response(200, json={"status": "ok"}))
    async with BiquoteClient(settings) as client:
        health = await client.health()
    assert health["status"] == "ok"


@respx.mock
async def test_get_ohlc_with_range(settings: Settings) -> None:
    route = respx.get(f"{BASE}/api/XAUUSD/ohlc").mock(
        return_value=httpx.Response(200, json={"symbol": "XAUUSD", "interval": "1d", "bars": []})
    )
    async with BiquoteClient(settings) as client:
        await client.get_ohlc(
            "XAUUSD",
            interval=Timeframe.D1,
            limit=10,
            start=datetime(2026, 1, 1, tzinfo=UTC),
            end=datetime(2026, 2, 1, tzinfo=UTC),
        )
    params = route.calls[0].request.url.params
    assert params["from"].startswith("2026-01-01")
    assert params["to"].startswith("2026-02-01")


@respx.mock
async def test_get_ohlc_rejects_bad_limit(settings: Settings) -> None:
    async with BiquoteClient(settings) as client:
        with pytest.raises(ValueError):
            await client.get_ohlc("XAUUSD", limit=5000)
        with pytest.raises(ValueError):
            await client.get_tick_history("XAUUSD", count=0)


@respx.mock
async def test_bad_request_raises_biquote_error(settings: Settings) -> None:
    respx.get(f"{BASE}/api/XAUUSD").mock(return_value=httpx.Response(400, json={"message": "bad"}))
    async with BiquoteClient(settings) as client:
        with pytest.raises(BiquoteError):
            await client.get_tick("XAUUSD")


@respx.mock
async def test_malformed_json_raises(settings: Settings) -> None:
    respx.get(f"{BASE}/api/XAUUSD").mock(return_value=httpx.Response(200, text="<html>nope</html>"))
    async with BiquoteClient(settings) as client:
        with pytest.raises(BiquoteError):
            await client.get_tick("XAUUSD")


@respx.mock
async def test_rate_limited_then_unavailable(settings: Settings) -> None:
    respx.get(f"{BASE}/api/XAUUSD").mock(
        return_value=httpx.Response(
            429, headers={"Retry-After": "0"}, json={"error": "rate_limited"}
        )
    )
    async with BiquoteClient(settings) as client:
        with pytest.raises(BiquoteUnavailableError):
            await client.get_tick("XAUUSD")


@respx.mock
async def test_transport_error_retried_then_unavailable(settings: Settings) -> None:
    respx.get(f"{BASE}/api/XAUUSD").mock(side_effect=httpx.ConnectError("boom"))
    async with BiquoteClient(settings) as client:
        with pytest.raises(BiquoteUnavailableError):
            await client.get_tick("XAUUSD")


@respx.mock
async def test_not_found_strict(settings: Settings) -> None:
    respx.get(f"{BASE}/api/XAUUSD").mock(
        return_value=httpx.Response(404, json={"message": "stale"})
    )
    async with BiquoteClient(settings) as client:
        with pytest.raises(BiquoteNotFoundError):
            await client.get_tick("XAUUSD", allow_stale=False)


@respx.mock
async def test_get_latest_empty_short_circuits(settings: Settings) -> None:
    async with BiquoteClient(settings) as client:
        assert await client.get_latest([]) == {}
