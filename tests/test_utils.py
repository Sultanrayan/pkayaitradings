"""Tests for shared utilities, config and schemas."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from shared.config import Settings
from shared.schemas.enums import Direction, MarketState, Timeframe
from shared.schemas.messages import Order, OrderSide, Position
from shared.utils.rate_limit import AsyncRateLimiter
from shared.utils.time import format_duration, parse_iso8601, timeframe_delta, utcnow


def test_settings_defaults() -> None:
    settings = Settings()
    assert settings.trading_symbols == ["XAUUSD", "BTCUSD"]
    assert settings.primary_timeframe is Timeframe.H1
    assert settings.analysis_timeframes[0] is Timeframe.M5


def test_settings_parses_csv_and_uppercases() -> None:
    settings = Settings(trading_symbols="eurusd, xauusd", analysis_timeframes="m5,h1")
    assert settings.trading_symbols == ["EURUSD", "XAUUSD"]
    assert settings.analysis_timeframes == [Timeframe.M5, Timeframe.H1]


def test_settings_accepts_json_list() -> None:
    settings = Settings(cors_origins='["http://a", "http://b"]')
    assert settings.cors_origins == ["http://a", "http://b"]


def test_settings_rejects_bad_weights() -> None:
    with pytest.raises(ValueError, match=r"sum to 1\.0"):
        Settings(weight_technical=0.5, weight_news=0.5, weight_risk=0.5)


def test_settings_rejects_bad_thresholds() -> None:
    with pytest.raises(ValueError, match="skip threshold"):
        Settings(decision_skip_threshold=0.9, decision_buy_threshold=0.5)


def test_timeframe_properties() -> None:
    assert Timeframe.M15.biquote_interval == "15m"
    assert Timeframe.H4.seconds == 14_400
    assert timeframe_delta(Timeframe.D1) == timedelta(days=1)


def test_parse_iso8601_handles_z() -> None:
    parsed = parse_iso8601("2026-02-24T10:30:00Z")
    assert parsed.tzinfo is not None
    assert parsed == datetime(2026, 2, 24, 10, 30, tzinfo=UTC)


def test_format_duration() -> None:
    assert format_duration(timedelta(hours=2, minutes=15)) == "2h 15m"
    assert format_duration(timedelta(minutes=45)) == "45m"
    assert format_duration(timedelta(seconds=30)) == "30s"
    assert format_duration(timedelta(seconds=-5)) == "0s"


def test_utcnow_is_aware() -> None:
    assert utcnow().tzinfo is UTC


async def test_rate_limiter_enforces_window() -> None:
    limiter = AsyncRateLimiter(max_calls=2, period_seconds=0.2)
    await limiter.acquire()
    await limiter.acquire()
    assert limiter.remaining == 0
    await limiter.acquire()  # blocks until the window resets
    assert limiter.remaining >= 0


def test_rate_limiter_rejects_bad_args() -> None:
    with pytest.raises(ValueError):
        AsyncRateLimiter(0, 1)
    with pytest.raises(ValueError):
        AsyncRateLimiter(1, 0)


def test_order_from_direction() -> None:
    order = Order.from_direction(symbol="XAUUSD", direction=Direction.BULLISH, quantity=1.0)
    assert order.side is OrderSide.BUY
    sell = Order.from_direction(symbol="XAUUSD", direction=Direction.BEARISH, quantity=1.0)
    assert sell.side is OrderSide.SELL
    with pytest.raises(ValueError, match="NEUTRAL"):
        Order.from_direction(symbol="XAUUSD", direction=Direction.NEUTRAL, quantity=1.0)


def test_position_unrealised_pnl() -> None:
    long = Position(symbol="XAUUSD", side=OrderSide.BUY, quantity=2.0, entry_price=100.0)
    assert long.unrealised_pnl(110.0) == pytest.approx(20.0)
    short = Position(symbol="XAUUSD", side=OrderSide.SELL, quantity=2.0, entry_price=100.0)
    assert short.unrealised_pnl(90.0) == pytest.approx(20.0)


def test_market_state_enum_values() -> None:
    assert MarketState.CLOSED.value == "closed"
    assert MarketState("open") is MarketState.OPEN
