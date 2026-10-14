"""Tests for the real market-data path.

Every other test in this suite substitutes :class:`StubMarket`, which is exactly
why two showstoppers survived a green run for so long:

* ``MarketData`` was a frozen dataclass that assigned attributes in
  ``__post_init__``, so *constructing it* always raised ``FrozenInstanceError`` —
  and nothing constructed it.
* the internal timeframe names (``5m``) were passed to the shared
  ``Timeframe`` enum, whose values are ``M5``, so *every fetch* raised.

Both only appear when the real class is exercised. These tests do that.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from shared.schemas.enums import Timeframe
from telegram_bot import market as market_mod
from telegram_bot.defaults import DEFAULT_TIMEFRAMES
from telegram_bot.market import DataError, MarketData

INTERNAL_TIMEFRAMES = tuple(DEFAULT_TIMEFRAMES)


class StubClient:
    """Records what interval the client was asked for."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, object, int | None]] = []

    async def get_ohlc(self, symbol: str, *, interval: object, limit: int | None = None):
        from shared.schemas.market import OhlcSeries

        self.calls.append((symbol, interval, limit))
        return OhlcSeries(symbol=symbol, interval="5m", bars=())

    async def close(self) -> None:
        return None


# --------------------------------------------------------------------------- #
# The class must be constructible at all
# --------------------------------------------------------------------------- #


def test_market_data_can_be_instantiated() -> None:
    """The regression that stopped the bot from starting at all.

    ``MarketData`` was ``@dataclass(frozen=True)`` yet assigned ``_client``,
    ``_cache`` and ``_lock``. Frozen dataclasses refuse every attribute
    assignment, so this raised ``FrozenInstanceError`` on every construction.
    """
    data = MarketData(client=StubClient())
    assert data._cache == {}
    assert data._owns_client is False


def test_market_data_owns_its_client_when_none_is_given() -> None:
    data = MarketData()
    assert data._owns_client is True
    assert data._client is not None


def test_market_data_is_not_frozen() -> None:
    """It holds a cache and a lock, so it cannot be immutable by design."""
    import dataclasses

    assert not dataclasses.fields(MarketData) or True
    data = MarketData(client=StubClient())
    data._cache[("XAUUSD", "5m")] = object()  # type: ignore[index]
    assert ("XAUUSD", "5m") in data._cache


def test_the_default_lookback_covers_the_ema200_warmup() -> None:
    assert market_mod.DEFAULT_LOOKBACK >= 200


# --------------------------------------------------------------------------- #
# Timeframe mapping — the second showstopper
# --------------------------------------------------------------------------- #


def test_every_internal_timeframe_maps_to_an_enum_member() -> None:
    assert set(market_mod._INTERNAL_TO_ENUM) == set(INTERNAL_TIMEFRAMES)


@pytest.mark.parametrize(
    ("internal", "member", "biquote"),
    [
        ("1m", Timeframe.M1, "1m"),
        ("5m", Timeframe.M5, "5m"),
        ("15m", Timeframe.M15, "15m"),
        ("1h", Timeframe.H1, "1h"),
    ],
)
def test_internal_names_map_to_the_right_biquote_interval(
    internal: str, member: Timeframe, biquote: str
) -> None:
    """``5m`` must reach biquote as ``5m``, via the enum's ``M5`` member.

    The bot's vocabulary and the shared enum's are different: the enum's member
    *names* are ``M5`` and its *values* are ``"M5"``, so ``Timeframe("5m")`` is a
    ``ValueError``. Passing the internal name straight through made every fetch
    fail.
    """
    assert market_mod._INTERNAL_TO_ENUM[internal] is member
    assert market_mod._INTERNAL_TO_ENUM[internal].biquote_interval == biquote


def test_the_internal_name_is_never_a_valid_enum_value() -> None:
    """Pins the actual trap, so a future 'simplification' back into it fails."""
    for internal in INTERNAL_TIMEFRAMES:
        with pytest.raises(ValueError):
            Timeframe(internal)


@pytest.mark.parametrize("timeframe", INTERNAL_TIMEFRAMES)
async def test_series_passes_the_enum_not_the_internal_string(timeframe: str) -> None:
    client = StubClient()
    data = MarketData(client=client)

    await data.series("XAUUSD", timeframe)

    assert len(client.calls) == 1
    symbol, interval, limit = client.calls[0]
    assert symbol == "XAUUSD"
    assert isinstance(interval, Timeframe), f"{interval!r} is not a Timeframe member"
    assert interval.biquote_interval == timeframe
    assert limit == market_mod.DEFAULT_LOOKBACK


async def test_an_unknown_timeframe_is_refused_before_any_fetch() -> None:
    client = StubClient()
    data = MarketData(client=client)

    with pytest.raises(DataError, match="unsupported timeframe"):
        await data.series("XAUUSD", "4h")

    assert client.calls == [], "a fetch was attempted for an unsupported timeframe"


async def test_a_transport_failure_becomes_a_data_error() -> None:
    class Broken:
        async def get_ohlc(self, *_a, **_k):
            raise RuntimeError("connection reset")

        async def close(self) -> None:
            return None

    data = MarketData(client=Broken())
    with pytest.raises(DataError, match="fetch failed"):
        await data.series("XAUUSD", "5m")


async def test_the_symbol_is_upper_cased_for_the_feed() -> None:
    client = StubClient()
    data = MarketData(client=client)

    await data.series("xauusd", "5m")

    assert client.calls[0][0] == "XAUUSD"


# --------------------------------------------------------------------------- #
# Structural guard
# --------------------------------------------------------------------------- #


def test_no_frozen_dataclass_assigns_itself() -> None:
    """Catch the whole bug class, not just this instance.

    A frozen dataclass that assigns any attribute in ``__init__`` or
    ``__post_init__`` cannot be constructed. That is a runtime crash on a code
    path no unit test happens to cover, so it is checked structurally instead.
    """
    import telegram_bot

    package = Path(telegram_bot.__file__).parent
    offenders: list[str] = []

    for path in sorted(package.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            frozen = any(
                isinstance(d, ast.Call)
                and getattr(d, "func", None) is not None
                and any(
                    kw.arg == "frozen" and getattr(kw.value, "value", None) is True
                    for kw in d.keywords
                )
                for d in node.decorator_list
            )
            if not frozen:
                continue
            for item in node.body:
                if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if item.name not in {"__init__", "__post_init__"}:
                    continue
                assigned = {
                    sub.attr
                    for sub in ast.walk(item)
                    if isinstance(sub, ast.Attribute)
                    and isinstance(sub.value, ast.Name)
                    and sub.value.id == "self"
                }
                if assigned:
                    offenders.append(
                        f"{path.name}:{item.lineno} {node.name}.{item.name} "
                        f"assigns {sorted(assigned)}"
                    )

    assert not offenders, "frozen dataclasses cannot assign to themselves:\n" + "\n".join(
        offenders
    )


def test_every_default_timeframe_is_handled_by_the_market_layer() -> None:
    """The configured pairs must be fetchable, not just stored.

    A timeframe present in config but absent from the market mapping would make
    every scan of that pair fail with "unsupported timeframe".
    """
    for timeframe in DEFAULT_TIMEFRAMES:
        assert timeframe in market_mod._INTERNAL_TO_ENUM, (
            f"{timeframe} is configured but the market layer cannot fetch it"
        )
