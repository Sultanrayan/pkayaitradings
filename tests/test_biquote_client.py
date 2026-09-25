"""Tests for the biquote REST client."""

from __future__ import annotations

import httpx
import pytest
import respx

from data_pipeline.biquote_client import BiquoteClient
from data_pipeline.errors import BiquoteNotFoundError, BiquoteUnavailableError
from shared.config import Settings
from shared.schemas.enums import Timeframe

BASE = "https://biquote.io"

TICK_PAYLOAD = {
    "symbol": "XAUUSD",
    "description": "Gold vs US Dollar",
    "bid": 2640.50,
    "ask": 2640.80,
    "mid": 2640.65,
    "spread": 0.30,
    "last": 0.0,
    "volume": 0,
    "high": 2650.0,
    "low": 2630.0,
    "direction": "UP",
    "dayDiffPercent": 0.42,
    "timestamp": "2026-02-24T10:30:00Z",
    "source": "MetaTrader 5 (Broker 1)",
    "marketState": "open",
    "stale": False,
    "quoteAgeSeconds": 0,
}


@respx.mock
async def test_get_tick_parses_and_maps_aliases(settings: Settings) -> None:
    route = respx.get(f"{BASE}/api/XAUUSD").mock(
        return_value=httpx.Response(200, json=TICK_PAYLOAD)
    )
    async with BiquoteClient(settings) as client:
        tick = await client.get_tick("xauusd")

    assert route.called
    assert tick.symbol == "XAUUSD"
    assert tick.mid == 2640.65
    assert tick.day_diff_percent == 0.42
    assert tick.is_tradeable is True


@respx.mock
async def test_get_latest_repeats_symbol_params(settings: Settings) -> None:
    route = respx.get(f"{BASE}/api/latest").mock(
        return_value=httpx.Response(
            200,
            json={
                "XAUUSD": TICK_PAYLOAD,
                "BTCUSD": {**TICK_PAYLOAD, "symbol": "BTCUSD", "mid": 68000.0},
            },
        )
    )
    async with BiquoteClient(settings) as client:
        ticks = await client.get_latest(["XAUUSD", "BTCUSD"])

    request = route.calls[0].request
    assert request.url.params.get_list("symbols") == ["XAUUSD", "BTCUSD"]
    assert set(ticks) == {"XAUUSD", "BTCUSD"}
    assert ticks["BTCUSD"].mid == 68000.0


@respx.mock
async def test_get_ohlc_reverses_to_oldest_first(settings: Settings) -> None:
    bars = [
        {
            "openTime": "2026-02-24T13:00:00Z",
            "open": 3,
            "high": 4,
            "low": 2,
            "close": 3.5,
            "volume": 0,
            "tickVolume": 10,
            "isOpen": True,
        },
        {
            "openTime": "2026-02-24T12:00:00Z",
            "open": 2,
            "high": 3,
            "low": 1,
            "close": 2.5,
            "volume": 0,
            "tickVolume": 12,
            "isOpen": False,
        },
        {
            "openTime": "2026-02-24T11:00:00Z",
            "open": 1,
            "high": 2,
            "low": 0.5,
            "close": 1.5,
            "volume": 0,
            "tickVolume": 8,
            "isOpen": False,
        },
    ]
    respx.get(f"{BASE}/api/XAUUSD/ohlc").mock(
        return_value=httpx.Response(200, json={"symbol": "XAUUSD", "interval": "1h", "bars": bars})
    )
    async with BiquoteClient(settings) as client:
        series = await client.get_ohlc("XAUUSD", interval=Timeframe.H1, limit=3)

    assert [bar.close for bar in series.bars] == [1.5, 2.5, 3.5]
    assert len(series.closed_bars) == 2
    assert series.latest_close == 3.5


@respx.mock
async def test_get_tick_raises_not_found(settings: Settings) -> None:
    respx.get(f"{BASE}/api/NOPE").mock(
        return_value=httpx.Response(404, json={"message": "No tick data available for 'NOPE'"})
    )
    async with BiquoteClient(settings) as client:
        with pytest.raises(BiquoteNotFoundError):
            await client.get_tick("NOPE")


@respx.mock
async def test_retries_then_succeeds_on_503(settings: Settings) -> None:
    route = respx.get(f"{BASE}/api/XAUUSD").mock(
        side_effect=[
            httpx.Response(503, headers={"Retry-After": "0"}),
            httpx.Response(200, json=TICK_PAYLOAD),
        ]
    )
    async with BiquoteClient(settings) as client:
        tick = await client.get_tick("XAUUSD")

    assert route.call_count == 2
    assert tick.symbol == "XAUUSD"


@respx.mock
async def test_raises_unavailable_after_exhausted_retries(settings: Settings) -> None:
    route = respx.get(f"{BASE}/api/XAUUSD").mock(
        return_value=httpx.Response(503, headers={"Retry-After": "0"})
    )
    async with BiquoteClient(settings) as client:
        with pytest.raises(BiquoteUnavailableError):
            await client.get_tick("XAUUSD")

    assert route.call_count == settings.biquote_max_retries + 1


@respx.mock
async def test_get_calendar_builds_filter_params(settings: Settings) -> None:
    route = respx.get(f"{BASE}/api/calendar").mock(return_value=httpx.Response(200, json=[]))
    async with BiquoteClient(settings) as client:
        await client.get_calendar(countries=["us", "eu"], importance=None, limit=50)

    params = route.calls[0].request.url.params
    assert params["countries"] == "US,EU"
    assert params["limit"] == "50"
