"""Tests for the Zenmux analysis card.

The upstream service returns a probability and nothing else. These tests pin the
three things that make the card trustworthy:

1. the classifier's contribution (direction, confidence) survives the mapping
   into a three-way headline,
2. structure, reasons and levels are computed from real bars rather than invented,
   and never contradict the price they are drawn against, and
3. nothing machine-readable leaks into a field the UI renders.
"""

from __future__ import annotations

import random
from typing import Any

import httpx
import pytest

from orchestrator.zenmux import (
    ANALYSIS_TIMEFRAMES,
    DEFAULT_MODEL,
    MODEL_TIMEFRAME,
    MODELS,
    ZENMUX_SYMBOL,
    ZENMUX_SYMBOL_DISPLAY,
    ZENMUX_TIMEFRAME,
    ZenmuxRequest,
    ZenmuxUnavailable,
    _direction_from,
    _fetch_candles,
    _resolve_model,
    _summary,
    answer_zenmux,
    display_models,
)
from orchestrator.zenmux_analysis import Bar, bars_from_candles
from shared.config import Settings
from shared.schemas.enums import Timeframe

# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


def _settings(**overrides: Any) -> Settings:
    base: dict[str, Any] = {
        "environment": "development",
        "llm_provider": "none",
        "zenmux_api_key": "sk-test-key",
    }
    base.update(overrides)
    return Settings(**base)


def _bars(count: int = 240, *, start: float = 4100.0, drift: float = 0.0) -> list[Bar]:
    """A deterministic bar series, optionally trending."""
    rng = random.Random(11)
    out: list[Bar] = []
    price = start
    for _ in range(count):
        open_ = price
        close = price + drift + rng.uniform(-1.2, 1.2)
        high = max(open_, close) + abs(rng.uniform(0, 1.0))
        low = min(open_, close) - abs(rng.uniform(0, 1.0))
        out.append(Bar(high=high, low=low, close=close))
        price = close
    return out


class _Series:
    def __init__(self, bars: list[Any]) -> None:
        self.bars = bars


class _RawBar:
    def __init__(self, index: int, *, is_open: bool = False) -> None:
        import datetime as _dt

        self.open_time = _dt.datetime(2026, 10, 4, 0, 0, tzinfo=_dt.UTC) + _dt.timedelta(
            minutes=5 * index
        )
        self.open = 4100.0 + index * 0.1
        self.high = 4100.5 + index * 0.1
        self.low = 4099.5 + index * 0.1
        self.close = 4100.2 + index * 0.1
        self.volume = 0.0
        self.tick_volume = 100
        self.is_open = is_open


class _Client:
    def __init__(self, bars: list[Any] | None = None) -> None:
        self._bars = bars if bars is not None else [_RawBar(i) for i in range(240)]
        self.calls: list[tuple[str, object]] = []

    async def get_ohlc(self, symbol: str, *, interval: object, limit: int) -> _Series:
        self.calls.append((symbol, interval))
        return _Series(self._bars[:limit])


_PAYLOAD: dict[str, Any] = {
    "object": "prediction",
    "backend": "xgboost",
    "as_of": "2026-10-04 06:55:00+00:00",
    "n_rows_built": 5752,
    "predictions": [
        {
            "prob_up": 0.6021714807,
            "prob_down": 0.3978285193,
            "signal": "BUY",
            "confidence": 0.2043429614,
        }
    ],
    "context": {"close": 4147.62, "forward_return": None, "atr": 3.44},
}


def _ok_client(monkeypatch, payload: dict[str, Any] | None = None) -> None:
    import orchestrator.zenmux as zenmux_mod

    body = payload if payload is not None else _PAYLOAD

    class _Ok:
        async def __aenter__(self) -> Any:
            return self

        async def __aexit__(self, *_exc: object) -> None:
            return None

        async def post(self, *_a: Any, **_k: Any) -> httpx.Response:
            return httpx.Response(200, json=body)

    monkeypatch.setattr(zenmux_mod.httpx, "AsyncClient", lambda **_k: _Ok())


# --------------------------------------------------------------------------- #
# Model registry — the two the UI may name, and nothing else
# --------------------------------------------------------------------------- #


def test_exactly_two_user_facing_models() -> None:
    assert set(MODELS) == {"super", "flash"}
    assert len(display_models()) == 2


def test_default_model_is_the_deep_one() -> None:
    assert DEFAULT_MODEL == "super"
    assert ZenmuxRequest(question="hi").model == "super"


def test_display_names_and_descriptions_match_the_spec() -> None:
    assert display_models() == [
        {"id": "super", "name": "Super Zenmux", "description": "Deep market analysis"},
        {"id": "flash", "name": "Flash Zenmux", "description": "Fast market analysis"},
    ]


def test_the_deep_model_is_the_larger_backend() -> None:
    """'Super' must not be the 3-tree model and 'Flash' the 91-tree one.

    Per the endpoint catalogue, xgboost has 91 trees and lightgbm 3, so the naming
    has to line up with reality or the labels are decorative.
    """
    assert MODELS["super"]["backend"] == "xgboost"
    assert MODELS["flash"]["backend"] == "lightgbm"


def test_the_model_catalogue_never_exposes_a_backend_name() -> None:
    """The selector is built from this, so a backend id here would reach the UI."""
    serialised = repr(display_models()).lower()
    for banned in ("xgboost", "lightgbm", "backend", "trees", "n_features"):
        assert banned not in serialised


def test_an_unknown_model_is_refused() -> None:
    with pytest.raises(ZenmuxUnavailable, match="Unknown analysis model"):
        _resolve_model("xgboost")


def test_a_raw_backend_name_cannot_be_smuggled_in() -> None:
    """A client bypassing the display layer must not be silently aliased."""
    with pytest.raises(ZenmuxUnavailable):
        _resolve_model("xgboost")
    with pytest.raises(ZenmuxUnavailable):
        _resolve_model("lightgbm")


# --------------------------------------------------------------------------- #
# Direction mapping
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("signal", "expected"),
    [("BUY", "BULLISH"), ("SELL", "BEARISH"), ("buy", "BULLISH"), ("sell", "BEARISH")],
)
def test_buy_and_sell_map_to_the_card_headlines(signal: str, expected: str) -> None:
    assert _direction_from(0.6, signal) == expected


# --------------------------------------------------------------------------- #
# Symbol, timeframe and candle handling
# --------------------------------------------------------------------------- #


def test_zenmux_is_xauusd_only() -> None:
    assert ZENMUX_SYMBOL == "XAUUSD"
    assert ZENMUX_SYMBOL_DISPLAY == "XAU/USD"


async def test_a_non_xauusd_symbol_is_refused() -> None:
    with pytest.raises(ZenmuxUnavailable, match="XAUUSD only"):
        await answer_zenmux(_settings(), _Client(), ZenmuxRequest(question="hi", symbol="BTCUSD"))


@pytest.mark.parametrize("timeframe", [Timeframe.H1, Timeframe.H4, Timeframe.D1])
async def test_an_unsupported_timeframe_is_refused(timeframe: Timeframe) -> None:
    """Only M5 and M15 have enough history behind them to read honestly."""
    with pytest.raises(ZenmuxUnavailable, match="cannot read"):
        await answer_zenmux(
            _settings(), _Client(), ZenmuxRequest(question="hi", timeframe=timeframe)
        )


async def test_m15_is_accepted(monkeypatch) -> None:
    """M15 aggregates to 96 bars from the ~288 M5 bars available, clearing the
    55-bar minimum a 50-period average needs."""
    _ok_client(monkeypatch)
    card = await answer_zenmux(
        _settings(), _Client(), ZenmuxRequest(question="hi", timeframe=Timeframe.M15)
    )
    assert card.timeframe == "M15"
    assert card.limited is False


def test_the_default_timeframe_is_m5() -> None:
    assert ZenmuxRequest(question="hi").timeframe is ZENMUX_TIMEFRAME


def test_only_m5_and_m15_are_offered() -> None:
    assert set(ANALYSIS_TIMEFRAMES) == {Timeframe.M5, Timeframe.M15}
    assert set(ANALYSIS_TIMEFRAMES.values()) == {"M5", "M15"}


def test_the_classifier_timeframe_is_pinned_to_m5() -> None:
    """The upstream 276-feature contract is anchored on M5 and is not client-controlled."""
    assert MODEL_TIMEFRAME == "M5"


async def test_open_bars_are_excluded() -> None:
    client = _Client([_RawBar(0), _RawBar(1, is_open=True)])
    candles = await _fetch_candles(client, "XAUUSD")
    assert len(candles) == 1


async def test_candles_carry_iso_timestamps_and_ohlc() -> None:
    candle = (await _fetch_candles(_Client(), "XAUUSD"))[0]
    assert candle["time"].endswith("Z")
    assert set(candle) >= {"time", "open", "high", "low", "close", "tick_volume"}


async def test_no_closed_bars_is_an_explicit_failure() -> None:
    client = _Client([_RawBar(0, is_open=True)])
    with pytest.raises(ZenmuxUnavailable, match="No closed M5 candles"):
        await _fetch_candles(client, "XAUUSD")


async def test_candles_are_requested_on_m5() -> None:
    client = _Client()
    await _fetch_candles(client, "XAUUSD")
    assert client.calls[0][1] is ZENMUX_TIMEFRAME


# --------------------------------------------------------------------------- #
# Failure modes — never fabricate
# --------------------------------------------------------------------------- #


async def test_an_unconfigured_key_is_a_clear_failure() -> None:
    with pytest.raises(ZenmuxUnavailable, match="ZENMUX_API_KEY"):
        await answer_zenmux(
            _settings(zenmux_api_key=""), _Client(), ZenmuxRequest(question="hi")
        )


async def test_an_upstream_error_is_a_clear_failure(monkeypatch) -> None:
    import orchestrator.zenmux as zenmux_mod

    class _Boom:
        async def __aenter__(self) -> Any:
            return self

        async def __aexit__(self, *_exc: object) -> None:
            return None

        async def post(self, *_a: Any, **_k: Any) -> httpx.Response:
            return httpx.Response(500, json={"error": "boom"})

    monkeypatch.setattr(zenmux_mod.httpx, "AsyncClient", lambda **_k: _Boom())

    with pytest.raises(ZenmuxUnavailable, match="HTTP 500"):
        await answer_zenmux(_settings(), _Client(), ZenmuxRequest(question="hi"))


async def test_a_transport_failure_is_a_clear_failure(monkeypatch) -> None:
    import orchestrator.zenmux as zenmux_mod

    class _Down:
        async def __aenter__(self) -> Any:
            return self

        async def __aexit__(self, *_exc: object) -> None:
            return None

        async def post(self, *_a: Any, **_k: Any) -> httpx.Response:
            raise httpx.ConnectError("refused")

    monkeypatch.setattr(zenmux_mod.httpx, "AsyncClient", lambda **_k: _Down())

    with pytest.raises(ZenmuxUnavailable, match="Could not reach"):
        await answer_zenmux(_settings(), _Client(), ZenmuxRequest(question="hi"))


async def test_a_malformed_upstream_body_is_a_clear_failure(monkeypatch) -> None:
    import orchestrator.zenmux as zenmux_mod

    class _Garbage:
        async def __aenter__(self) -> Any:
            return self

        async def __aexit__(self, *_exc: object) -> None:
            return None

        async def post(self, *_a: Any, **_k: Any) -> httpx.Response:
            return httpx.Response(200, text="<html>not json</html>")

    monkeypatch.setattr(zenmux_mod.httpx, "AsyncClient", lambda **_k: _Garbage())

    with pytest.raises(ZenmuxUnavailable, match="malformed"):
        await answer_zenmux(_settings(), _Client(), ZenmuxRequest(question="hi"))


async def test_an_empty_prediction_list_is_a_clear_failure(monkeypatch) -> None:
    import orchestrator.zenmux as zenmux_mod

    class _Empty:
        async def __aenter__(self) -> Any:
            return self

        async def __aexit__(self, *_exc: object) -> None:
            return None

        async def post(self, *_a: Any, **_k: Any) -> httpx.Response:
            return httpx.Response(200, json={"predictions": [], "context": {}})

    monkeypatch.setattr(zenmux_mod.httpx, "AsyncClient", lambda **_k: _Empty())

    with pytest.raises(ZenmuxUnavailable, match="no prediction"):
        await answer_zenmux(_settings(), _Client(), ZenmuxRequest(question="hi"))


async def test_an_unknown_model_is_refused_before_any_call() -> None:
    client = _Client()
    with pytest.raises(ZenmuxUnavailable, match="Unknown analysis model"):
        await answer_zenmux(_settings(), client, ZenmuxRequest(question="hi", model="catboost"))
    assert client.calls == [], "no candles should be fetched for an invalid model"


# --------------------------------------------------------------------------- #
# The card itself
# --------------------------------------------------------------------------- #


async def test_the_card_carries_the_classifier_numbers(monkeypatch) -> None:
    _ok_client(monkeypatch)
    card = await answer_zenmux(_settings(), _Client(), ZenmuxRequest(question="hi"))

    assert card.direction == "BULLISH"
    assert card.confidence == pytest.approx(0.2043429614)
    assert card.probability_up == pytest.approx(0.6021714807)
    assert card.probability_down == pytest.approx(0.3978285193)


async def test_the_flash_model_is_reported_by_its_display_name(monkeypatch) -> None:
    _ok_client(monkeypatch)
    card = await answer_zenmux(
        _settings(), _Client(), ZenmuxRequest(question="hi", model="flash")
    )
    assert card.model_name == "Flash Zenmux"
    assert card.model_description == "Fast market analysis"


async def test_no_jargon_reaches_the_client(monkeypatch) -> None:
    """Backend names, thresholds and feature counts are internals, not content."""
    _ok_client(monkeypatch)
    card = await answer_zenmux(_settings(), _Client(), ZenmuxRequest(question="hi"))

    serialised = card.model_dump_json().lower()
    for banned in ("xgboost", "lightgbm", "threshold", "n_rows_built", "backend", "feature"):
        assert banned not in serialised, f"{banned!r} leaked into the card"


async def test_the_response_model_has_no_jargon_fields() -> None:
    card = await _sample_card()
    fields = set(ZenmuxRequest.model_fields) | set(type(card).model_fields)
    for banned in ("backend", "threshold", "n_rows_built"):
        assert banned not in fields


async def _sample_card() -> Any:
    import orchestrator.zenmux as zenmux_mod

    original = zenmux_mod.httpx.AsyncClient

    class _Ok:
        async def __aenter__(self) -> Any:
            return self

        async def __aexit__(self, *_exc: object) -> None:
            return None

        async def post(self, *_a: Any, **_k: Any) -> httpx.Response:
            return httpx.Response(200, json=_PAYLOAD)

    zenmux_mod.httpx.AsyncClient = lambda **_k: _Ok()  # type: ignore[assignment]
    try:
        return await answer_zenmux(_settings(), _Client(), ZenmuxRequest(question="hi"))
    finally:
        zenmux_mod.httpx.AsyncClient = original  # type: ignore[assignment]


async def test_the_card_carries_indicator_fields(monkeypatch) -> None:
    _ok_client(monkeypatch)
    card = await answer_zenmux(_settings(), _Client(), ZenmuxRequest(question="hi"))

    assert card.structure in {"Bullish", "Bearish", "Neutral"}
    assert card.structure_detail
    assert card.atr is not None and card.atr > 0
    assert card.rsi is not None and 0 <= card.rsi <= 100
    assert card.updated_at


async def test_levels_bracket_the_close(monkeypatch) -> None:
    """Support below and resistance above price, or the card draws a wrong ladder."""
    _ok_client(monkeypatch)
    card = await answer_zenmux(_settings(), _Client(), ZenmuxRequest(question="hi"))

    assert card.support < card.close < card.resistance


async def test_every_reason_declares_its_source(monkeypatch) -> None:
    """One engine's output must not be presented as another's."""
    _ok_client(monkeypatch)
    card = await answer_zenmux(_settings(), _Client(), ZenmuxRequest(question="hi"))

    assert card.reasons
    for reason in card.reasons:
        assert reason.source in {"analysis", "model"}
        assert reason.detail.strip()


async def test_the_models_leaning_is_tagged_as_the_model(monkeypatch) -> None:
    _ok_client(monkeypatch)
    card = await answer_zenmux(_settings(), _Client(), ZenmuxRequest(question="hi"))

    model_reasons = [reason for reason in card.reasons if reason.source == "model"]
    assert len(model_reasons) == 1
    assert "Super Zenmux" in model_reasons[0].detail
    assert "leans" in model_reasons[0].detail


async def test_probabilities_are_clamped_into_range(monkeypatch) -> None:
    """A bad upstream value would render as a percentage above 100."""
    payload = {
        **_PAYLOAD,
        "predictions": [
            {"prob_up": 1.4, "prob_down": -0.4, "signal": "BUY", "confidence": 2.5}
        ],
    }
    _ok_client(monkeypatch, payload)
    card = await answer_zenmux(_settings(), _Client(), ZenmuxRequest(question="hi"))

    assert 0.0 <= card.probability_up <= 1.0
    assert 0.0 <= card.probability_down <= 1.0
    assert 0.0 <= card.confidence <= 1.0


async def test_a_full_history_is_not_flagged_as_limited(monkeypatch) -> None:
    _ok_client(monkeypatch)
    card = await answer_zenmux(_settings(), _Client(), ZenmuxRequest(question="hi"))
    assert card.limited is False


async def test_a_short_history_is_flagged_rather_than_guessed(monkeypatch) -> None:
    """Too few bars must produce an explicit reduced state, not a confident read."""
    _ok_client(monkeypatch)
    client = _Client([_RawBar(i) for i in range(20)])
    card = await answer_zenmux(_settings(), client, ZenmuxRequest(question="hi"))

    assert card.limited is True
    assert card.structure == "Neutral"
    assert card.structure_detail == "Not enough closed bars to read structure"
    # Geometry must still hold so the card renders.
    assert card.support < card.close < card.resistance


async def test_the_summary_names_no_internals(monkeypatch) -> None:
    _ok_client(monkeypatch)
    card = await answer_zenmux(_settings(), _Client(), ZenmuxRequest(question="hi"))

    lowered = card.summary.lower()
    assert "xau/usd" in lowered
    for banned in ("xgboost", "lightgbm", "threshold", "backend", "feature"):
        assert banned not in lowered


def test_the_summary_helper_reads_as_plain_english() -> None:
    text = _summary(
        "BEARISH", 0.2, 4147.62, "M15", "Lower highs and lower lows", 4100.0, 4200.0
    )
    assert "Bearish" in text
    assert "XAU/USD" in text
    assert "M15" in text
    assert "4147.62" in text
    assert "4100.00" in text
    assert "4200.00" in text


# --------------------------------------------------------------------------- #
# Candle shaping for the indicator pass
# --------------------------------------------------------------------------- #


def test_bars_from_candles_extracts_ohlc() -> None:
    bars = bars_from_candles([{"high": 2.0, "low": 1.0, "close": 1.5, "open": 1.2}])
    assert bars == [Bar(high=2.0, low=1.0, close=1.5)]
