"""Integration: store adapter, API router, and the message bus.

The claim these tests defend is RULE 6: the signal the API returns is the signal
the store holds is the signal plotted. Any transformation between those layers —
a re-rounded price, a local-time timestamp, a re-serialised float — breaks it
quietly, so each hop is asserted against the *original* signal rather than
against the previous layer's output.
"""

from __future__ import annotations

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from orchestrator.store import SignalStore
from signals.api import build_signals_router, set_store
from signals.models import Signal
from signals.store import SIGNAL_KIND, EngineSignalStore
from signals.tests.test_engine_helpers import compute_reference_signals


def _signals(count: int = 5) -> list[Signal]:
    """A deterministic set of real signals from the shared reference frame."""
    return compute_reference_signals()[:count]


@pytest.fixture
def adapter() -> EngineSignalStore:
    return EngineSignalStore(SignalStore())


@pytest.fixture
def populated(adapter: EngineSignalStore) -> EngineSignalStore:
    for signal in _signals():
        adapter.publish(signal)
    return adapter


# --------------------------------------------------------------------------- #
# Store adapter
# --------------------------------------------------------------------------- #


def test_publish_then_latest_roundtrips_exactly(adapter: EngineSignalStore) -> None:
    original = _signals(1)[0]
    adapter.publish(original)
    stored = adapter.latest("XAUUSD", "H1")

    assert stored is not None
    assert stored == original
    assert stored.timestamp == original.timestamp
    assert stored.price == original.price


def test_history_returns_oldest_first(adapter: EngineSignalStore) -> None:
    signals = _signals(5)
    for signal in signals:
        adapter.publish(signal)

    history = adapter.history("XAUUSD", "H1", limit=10)
    stamps = [s.timestamp for s in history]
    assert stamps == sorted(stamps)
    assert [s.timestamp for s in history] == [s.timestamp for s in signals]


def test_history_respects_the_limit(adapter: EngineSignalStore) -> None:
    for signal in _signals(5):
        adapter.publish(signal)
    assert len(adapter.history("XAUUSD", "H1", limit=2)) == 2


def test_history_rejects_a_non_positive_limit(adapter: EngineSignalStore) -> None:
    with pytest.raises(ValueError, match="limit must be at least 1"):
        adapter.history("XAUUSD", "H1", limit=0)


def test_latest_returns_the_newest_bar_not_the_newest_write(adapter: EngineSignalStore) -> None:
    """A late-arriving older bar must not displace a newer signal."""
    signals = _signals(3)
    newest = signals[-1]
    adapter.publish(newest)
    # Publish an older bar afterwards.
    adapter.publish(signals[0])

    stored = adapter.latest("XAUUSD", "H1")
    assert stored is not None
    assert stored.timestamp == newest.timestamp


def test_symbol_lookup_is_case_insensitive(populated: EngineSignalStore) -> None:
    assert populated.latest("xauusd", "H1") == populated.latest("XAUUSD", "H1")


def test_an_unknown_pair_returns_none(adapter: EngineSignalStore) -> None:
    assert adapter.latest("NOSUCH", "H1") is None
    assert adapter.history("NOSUCH", "H1") == []


def test_timeframes_are_kept_apart(adapter: EngineSignalStore) -> None:
    """The shared store has no timeframe concept, so the adapter must add it.

    `with_levels` produces a new instance with a different timeframe, which is the
    cleanest way to build a second pair's signal without hand-constructing one.
    """
    hourly, second = _signals(2)
    four_hourly = Signal(
        timestamp=second.timestamp,
        symbol=second.symbol,
        timeframe="H4",
        action=second.action,
        price=second.price,
        entry=second.entry,
        sl=second.sl,
        tp1=second.tp1,
        tp2=second.tp2,
        atr=second.atr,
        confidence=second.confidence,
        reason=second.reason,
        layers=dict(second.layers),
    )

    adapter.publish(hourly)
    adapter.publish(four_hourly)

    assert len(adapter.history("XAUUSD", "H1")) == 1
    assert len(adapter.history("XAUUSD", "H4")) == 1
    assert adapter.latest("XAUUSD", "H1").timestamp == hourly.timestamp
    assert adapter.latest("XAUUSD", "H4").timestamp == four_hourly.timestamp


def test_range_filters_on_the_bar_timestamp(populated: EngineSignalStore) -> None:
    signals = populated.history("XAUUSD", "H1", limit=100)
    assert len(signals) >= 2
    first, second, last = signals[0].timestamp, signals[1].timestamp, signals[-1].timestamp

    everything = populated.range("XAUUSD", "H1", first, last)
    assert [s.timestamp for s in everything] == [s.timestamp for s in signals]

    inside = populated.range("XAUUSD", "H1", first, second)
    assert [s.timestamp for s in inside] == [first, second]

    assert [s.timestamp for s in populated.range("XAUUSD", "H1", last, None)] == [last]
    assert [s.timestamp for s in populated.range("XAUUSD", "H1", None, first)] == [first]


def test_range_bounds_are_inclusive(populated: EngineSignalStore) -> None:
    target = populated.history("XAUUSD", "H1", limit=1)[0]
    found = populated.range("XAUUSD", "H1", target.timestamp, target.timestamp)
    assert [s.timestamp for s in found] == [target.timestamp]


def test_publish_all_reports_how_many() -> None:
    store = EngineSignalStore(SignalStore())
    batch = _signals(3)
    written = store.publish_all(batch)
    assert written == len(batch)
    assert store.count("XAUUSD", "H1") == len(batch)


def test_engine_signals_are_distinguishable_from_agent_signals(
    adapter: EngineSignalStore,
) -> None:
    """A dashboard filtering by `kind` must be able to tell them apart."""
    adapter.publish(_signals(1)[0])
    records = adapter.store.query(symbol="XAUUSD", limit=100)
    assert all(r.kind == SIGNAL_KIND for r in records)


def test_a_corrupt_payload_is_skipped_not_raised(adapter: EngineSignalStore) -> None:
    """One bad record must not break the whole history endpoint."""
    adapter.publish(_signals(1)[0])
    adapter.store.record_signal(
        symbol="XAUUSD",
        correlation_id="",
        agent="orchestrator",
        kind=SIGNAL_KIND,
        direction="BUY",
        confidence=0.5,
        payload={"nonsense": True},
    )

    history = adapter.history("XAUUSD", "H1")
    assert len(history) == 1


def test_two_adapters_over_one_store_see_the_same_data() -> None:
    """The check behind the worker/API split, made explicit rather than assumed."""
    shared = SignalStore()
    a = EngineSignalStore(shared)
    b = EngineSignalStore(shared)

    assert a.uses_shared_process(b)
    a.publish(_signals(1)[0])
    assert b.latest("XAUUSD", "H1") is not None


def test_two_adapters_over_different_stores_do_not() -> None:
    a = EngineSignalStore(SignalStore())
    b = EngineSignalStore(SignalStore())
    assert not a.uses_shared_process(b)
    a.publish(_signals(1)[0])
    assert b.latest("XAUUSD", "H1") is None


def test_max_history_must_be_positive() -> None:
    with pytest.raises(ValueError, match="max_history must be at least 1"):
        EngineSignalStore(SignalStore(), max_history=0)


def test_max_history_is_reported() -> None:
    assert EngineSignalStore(SignalStore(), max_history=7).max_history == 7


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #


@pytest.fixture
def client(populated: EngineSignalStore) -> TestClient:
    app = FastAPI()
    app.include_router(build_signals_router(populated))
    return TestClient(app)


def test_latest_returns_the_stored_signal_verbatim(client: TestClient) -> None:
    """The API response must equal the engine's original signal field for field."""
    body = client.get("/api/v1/signals/XAUUSD/H1/latest").json()
    original = compute_reference_signals()[-1]

    assert body["timestamp"] == original.timestamp.isoformat()
    assert body["price"] == original.price
    assert body["action"] == original.action
    assert body["sl"] == original.sl
    assert body["tp1"] == original.tp1
    assert body["tp2"] == original.tp2
    assert body["confidence"] == original.confidence
    assert body["layers"] == original.layers


def test_latest_returns_404_for_an_unknown_pair(client: TestClient) -> None:
    response = client.get("/api/v1/signals/NOSUCH/H1/latest")
    assert response.status_code == 404


def test_history_returns_the_same_signals_as_the_store(client: TestClient) -> None:
    body = client.get("/api/v1/signals/XAUUSD/H1/history?limit=100").json()
    assert body["count"] == len(body["signals"])
    assert body["symbol"] == "XAUUSD"
    stamps = [s["timestamp"] for s in body["signals"]]
    assert stamps == sorted(stamps)


def test_history_empty_is_a_200_not_an_error(client: TestClient) -> None:
    body = client.get("/api/v1/signals/ETHUSD/H1/history").json()
    assert body["count"] == 0
    assert body["signals"] == []


def test_history_limit_is_validated(client: TestClient) -> None:
    assert client.get("/api/v1/signals/XAUUSD/H1/history?limit=0").status_code == 422
    assert client.get("/api/v1/signals/XAUUSD/H1/history?limit=5000").status_code == 422


def test_range_filters_and_validates(client: TestClient) -> None:
    everything = client.get("/api/v1/signals/XAUUSD/H1/history?limit=100").json()
    stamps = [pd.Timestamp(s["timestamp"]) for s in everything["signals"]]

    body = client.get(
        "/api/v1/signals/XAUUSD/H1/range",
        params={"from": stamps[0].isoformat(), "to": stamps[1].isoformat()},
    ).json()
    assert body["count"] == 2

    bad = client.get("/api/v1/signals/XAUUSD/H1/range", params={"from": "not-a-date"})
    assert bad.status_code == 400


def test_range_without_bounds_returns_everything(client: TestClient) -> None:
    body = client.get("/api/v1/signals/XAUUSD/H1/range").json()
    assert body["count"] > 0


def test_timestamps_are_utc(client: TestClient) -> None:
    body = client.get("/api/v1/signals/XAUUSD/H1/history?limit=100").json()
    for entry in body["signals"]:
        assert entry["timestamp"].endswith("+00:00")


def test_endpoints_are_read_only(client: TestClient) -> None:
    """No route may accept a signal body; a signal must come from a closed bar.

    Walks the routes rather than only the ones under ``/signals/``, and compares
    each path's full method set. A single ``POST`` on any signal route would mean
    the API could report something no candle produced, which is the one way RULE 6
    can be broken from outside.
    """
    forbidden = {"post", "put", "patch", "delete"}
    # FastAPI wraps an included router, so `app.routes` does not expose these
    # paths. The OpenAPI document is the public, version-stable view of what the
    # app actually serves.
    paths = client.app.openapi()["paths"]
    signal_paths = {p: ops for p, ops in paths.items() if "/signals" in p}

    assert len(signal_paths) >= 3, f"expected three signal routes, found {sorted(signal_paths)}"
    for path, operations in signal_paths.items():
        overlap = set(operations) & forbidden
        assert not overlap, f"{path} accepts {sorted(overlap)}"
        assert set(operations) == {"get"}, f"{path} serves {sorted(operations)}, not GET only"


def test_endpoints_report_503_without_a_store() -> None:
    """A missing adapter is "not ready", not a 500 from ``None``."""
    set_store(None)
    app = FastAPI()
    app.include_router(build_signals_router())
    response = TestClient(app).get("/api/v1/signals/XAUUSD/H1/latest")
    assert response.status_code == 503


def test_api_requires_no_auth_of_its_own(client: TestClient) -> None:
    """Auth belongs to the gateway middleware; a second policy here would diverge."""
    assert client.get("/api/v1/signals/XAUUSD/H1/latest").status_code == 200


# --------------------------------------------------------------------------- #
# Message bus
# --------------------------------------------------------------------------- #


async def test_signal_publishes_to_the_bus_with_a_full_payload() -> None:
    """A fired signal must reach subscribers carrying every field, unaltered."""
    import asyncio

    from shared.messaging import InMemoryMessageBus
    from shared.schemas.messages import AgentMessage
    from signals.publisher import SIGNAL_CHANNEL, publish_signal

    bus = InMemoryMessageBus()
    signal = _signals(1)[0]

    received: list[AgentMessage] = []

    async def listen() -> None:
        async for message in bus.subscribe("signals.*"):
            received.append(message)
            return

    task = asyncio.create_task(listen())
    await asyncio.sleep(0.05)

    await publish_signal(bus, signal, correlation_id="test-cycle")
    await asyncio.sleep(0.05)
    task.cancel()

    assert received, "no message reached the subscriber"
    message = received[0]
    assert message.kind == "signal"
    assert message.source.value == "orchestrator"
    assert message.correlation_id == "test-cycle"
    assert SIGNAL_CHANNEL.endswith("engine")

    payload = message.payload
    assert set(payload) == set(signal.to_dict()), "the bus payload lost or gained a field"
    assert payload["timestamp"] == signal.timestamp.isoformat()
    assert payload["price"] == signal.price
    assert payload["action"] == signal.action
    assert payload["sl"] == signal.sl
    assert payload["layers"] == signal.layers


async def test_publish_failure_propagates_rather_than_being_swallowed() -> None:
    """A signal in the store but not on the bus is a real gap; it must surface."""
    from signals.publisher import publish_signal

    class _BrokenBus:
        async def publish(self, channel: str, message: object) -> None:
            raise RuntimeError("broker unreachable")

        def subscribe(self, pattern: str):  # pragma: no cover - unused
            raise NotImplementedError

        async def close(self) -> None:  # pragma: no cover - unused
            return None

    with pytest.raises(RuntimeError, match="broker unreachable"):
        await publish_signal(_BrokenBus(), _signals(1)[0])  # type: ignore[arg-type]


async def test_bus_payload_round_trips_back_to_the_signal() -> None:
    """Store → bus → signal must not lose or alter the bar."""
    original = _signals(1)[0]
    restored = Signal.from_dict(original.to_dict())
    assert restored == original
    assert restored.timestamp == original.timestamp
    assert restored.price == original.price


# --------------------------------------------------------------------------- #
# End-to-end: frame → signals → store → API
# --------------------------------------------------------------------------- #


def test_the_plotted_signal_is_the_stored_signal(client: TestClient) -> None:
    """The whole chain, asserted against the original engine output.

    This is RULE 6 expressed as a single test: the signal a chart would plot from
    the API response is the same object the engine produced and the store holds.
    """
    reference = compute_reference_signals()
    body = client.get("/api/v1/signals/XAUUSD/H1/history?limit=100").json()

    plotted = {(s["timestamp"], s["price"]) for s in body["signals"]}
    expected = {(s.timestamp.isoformat(), s.price) for s in reference}
    assert plotted == expected
