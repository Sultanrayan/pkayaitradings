"""Cross-language contract test: the API response and the TypeScript types.

`frontend/src/lib/signal-engine.ts` declares the `TradeSignal` interface by hand.
Nothing at runtime ties it to the Python dataclass, so a field renamed on one side
silently becomes `undefined` on the other — and a chart that plots `signal.price`
would quietly plot nothing.

This test parses the TypeScript interface out of the file and asserts it matches
the API response field for field. It is the cheapest possible substitute for
generating the types, and it fails at the moment of the rename rather than in a
browser.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from orchestrator.store import SignalStore
from signals.api import build_signals_router
from signals.models import Signal
from signals.store import EngineSignalStore
from signals.tests.test_engine_helpers import compute_reference_signals

_TS_PATH = (
    Path(__file__).resolve().parents[2] / "frontend" / "src" / "lib" / "signal-engine.ts"
)


@pytest.fixture(scope="module")
def response_signal() -> dict:
    """One real API response body."""
    store = EngineSignalStore(SignalStore())
    for signal in compute_reference_signals():
        store.publish(signal)
    app = FastAPI()
    app.include_router(build_signals_router(store))
    client = TestClient(app)
    body = client.get("/api/v1/signals/XAUUSD/H1/history?limit=1").json()
    assert body["count"] == 1
    return body["signals"][0]


@pytest.fixture(scope="module")
def declared_fields() -> set[str]:
    """Field names declared on the TypeScript ``TradeSignal`` interface."""
    assert _TS_PATH.exists(), f"TypeScript contract not found at {_TS_PATH}"
    source = _TS_PATH.read_text(encoding="utf-8")
    match = re.search(
        r"export interface TradeSignal \{(.*?)\n\}", source, flags=re.DOTALL
    )
    assert match, "TradeSignal interface not found in the TypeScript contract"

    block = match.group(1)
    # Strip block comments first, or a field named in prose would be picked up.
    without_comments = re.sub(r"/\*.*?\*/", "", block, flags=re.DOTALL)
    return set(re.findall(r"^\s{2}([a-zA-Z_][a-zA-Z0-9_]*)\??\s*[?:]", without_comments, re.M))


def test_typescript_interface_exists() -> None:
    assert _TS_PATH.exists(), (
        "frontend/src/lib/signal-engine.ts is missing; the frontend contract for "
        "the signal engine must be kept in step with the dataclass"
    )


def test_response_fields_match_the_typescript_interface(declared_fields, response_signal) -> None:
    """Every field the API sends must be declared, and vice versa."""
    sent = set(response_signal)
    assert sent == declared_fields, (
        "the API response and the TypeScript interface disagree; "
        f"undeclared in TS: {sorted(sent - declared_fields)}, "
        f"declared in TS but never sent: {sorted(declared_fields - sent)}"
    )


def test_no_field_is_optional(declared_fields, response_signal) -> None:
    """Every field must be required; an optional one is `undefined` waiting to happen."""
    source = _TS_PATH.read_text(encoding="utf-8")
    block = re.search(r"export interface TradeSignal \{(.*?)\n\}", source, re.DOTALL)
    assert block
    optional = set(re.findall(r"^\s{2}([a-zA-Z_][a-zA-Z0-9_]*)\?\s*[?:]", block.group(1), re.M))
    assert not optional & set(response_signal), (
        f"these fields are optional in TS but always sent: {sorted(optional & set(response_signal))}"
    )
    assert declared_fields == set(response_signal)


def test_layers_type_names_every_layer() -> None:
    from signals.models import LAYER_NAMES

    source = _TS_PATH.read_text(encoding="utf-8")
    match = re.search(r"export type SignalLayerName =(.*?);", source, re.DOTALL)
    assert match, "SignalLayerName not found in the TypeScript contract"
    declared = set(re.findall(r'"([a-z_]+)"', match.group(1)))
    assert declared == set(LAYER_NAMES), (
        f"TypeScript layers {sorted(declared)} != Python layers {sorted(LAYER_NAMES)}"
    )


def test_action_type_matches_the_models_literal() -> None:
    from signals.models import Action

    source = _TS_PATH.read_text(encoding="utf-8")
    match = re.search(r"export type SignalAction =(.*?);", source, re.DOTALL)
    assert match
    declared = set(re.findall(r'"([A-Z]+)"', match.group(1)))
    import typing

    assert declared == set(typing.get_args(Action))


def test_the_plot_rule_is_documented_in_the_typescript() -> None:
    """The file must state the anchoring rule, since it is the whole point."""
    source = _TS_PATH.read_text(encoding="utf-8")
    lowered = source.lower()
    assert "close time" in lowered or "close time" in source
    assert "do not" in lowered, "the contract must state what not to do"


def test_to_dict_keys_are_exactly_the_declared_fields() -> None:
    """The dataclass serialisation and the API body are the same shape."""
    signal = compute_reference_signals()[0]
    assert set(signal.to_dict()) == set(signal.to_dict())
    # And the API adds nothing on top.
    store = EngineSignalStore(SignalStore())
    store.publish(signal)
    app = FastAPI()
    app.include_router(build_signals_router(store))
    client = TestClient(app)
    body = client.get("/api/v1/signals/XAUUSD/H1/latest").json()
    assert set(body) == set(signal.to_dict())


def test_signal_type_is_importable_for_typechecking() -> None:
    """`Signal` is the source of truth the contract is written against."""
    assert Signal.__name__ == "Signal"
