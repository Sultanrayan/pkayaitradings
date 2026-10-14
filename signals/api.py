"""FastAPI router for the signal engine's read endpoints.

Read-only by design. There is no ``POST`` to create a signal: signals are
produced by the engine on closed bars and published by the scheduler, and an
endpoint that accepted a signal body would break RULE 6 — the API would be able
to report something that no bar ever produced.

The response body is :meth:`Signal.to_dict` verbatim. No rounding, no field
renaming, no timestamp reformatting. The chart therefore plots the same values
the store holds, which is the only way "API == store == chart" is verifiable.

Authentication is not applied here. The gateway's ``enforce_auth`` middleware
already requires a bearer token for every ``/api/`` path that is not in its
public list, so a router-level check would be a second, divergent copy of the
same policy.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from shared.logging import get_logger
from signals.models import Signal
from signals.store import EngineSignalStore

_logger = get_logger(__name__)

__all__ = ["build_signals_router", "get_store", "set_store"]

#: Process-local adapter. Set once at startup by :func:`set_store`.
_store: EngineSignalStore | None = None


def set_store(store: EngineSignalStore | None) -> None:
    """Install the adapter the endpoints read from.

    Args:
        store: The adapter, or ``None`` to clear it.
    """
    global _store
    _store = store


def get_store() -> EngineSignalStore:
    """Return the installed adapter.

    Raises:
        HTTPException: 503 when no adapter has been installed, so a caller gets a
            clear "not ready" rather than a 500 from an ``AttributeError`` on
            ``None``.
    """
    if _store is None:
        raise HTTPException(
            status_code=503,
            detail="signal store not initialised",
        )
    return _store


async def latest(symbol: str, timeframe: str) -> dict[str, Any]:
    """Most recent signal for a symbol and timeframe.

    Args:
        symbol: Instrument ticker; case-insensitive.
        timeframe: Candle interval, e.g. ``H1``.

    Returns:
        The signal as JSON.

    Raises:
        HTTPException: 404 when no signal has been published for the pair.
    """
    signal = get_store().latest(symbol, timeframe)
    if signal is None:
        raise HTTPException(
            status_code=404,
            detail=f"no signal for {symbol.upper()} {timeframe}",
        )
    return signal.to_dict()


async def history(
    symbol: str,
    timeframe: str,
    limit: int = Query(default=100, ge=1, le=1000),
) -> dict[str, Any]:
    """Recent signals for a symbol and timeframe.

    Args:
        symbol: Instrument ticker; case-insensitive.
        timeframe: Candle interval.
        limit: Maximum signals returned, 1 to 1000 inclusive.

    Returns:
        ``{"symbol", "timeframe", "count", "signals"}`` with signals oldest
        first. An empty list is a 200 with ``count: 0``; "nothing yet" is a
        normal state, not an error.
    """
    signals = get_store().history(symbol, timeframe, limit)
    return {
        "symbol": symbol.upper(),
        "timeframe": timeframe,
        "count": len(signals),
        "signals": [signal.to_dict() for signal in signals],
    }


async def range_query(
    symbol: str,
    timeframe: str,
    from_: str | None = Query(default=None, alias="from"),
    to: str | None = Query(default=None),
) -> dict[str, Any]:
    """Signals whose bar timestamp falls within an inclusive range.

    Args:
        symbol: Instrument ticker; case-insensitive.
        timeframe: Candle interval.
        from_: Inclusive lower bound on the bar timestamp, ISO-8601. Optional.
        to: Inclusive upper bound on the bar timestamp, ISO-8601. Optional.

    Returns:
        ``{"symbol", "timeframe", "count", "signals"}`` with signals oldest
        first.

    Raises:
        HTTPException: 400 when a bound cannot be parsed. Reading back the
            message from the store adapter is not enough here: an unparsable
            bound silently becoming "unbounded" would return the whole history
            and the caller would have no way to tell.
    """
    store = get_store()
    for label, value in (("from", from_), ("to", to)):
        if value is None or value == "":
            continue
        try:
            import pandas as pd

            pd.Timestamp(value)
        except (ValueError, TypeError) as exc:
            raise HTTPException(
                status_code=400,
                detail=f"invalid {label} timestamp: {value!r}",
            ) from exc

    signals = store.range(symbol, timeframe, from_, to)
    return {
        "symbol": symbol.upper(),
        "timeframe": timeframe,
        "count": len(signals),
        "signals": [signal.to_dict() for signal in signals],
    }


def build_signals_router(store: EngineSignalStore | None = None) -> APIRouter:
    """Build the signals router, optionally installing a store.

    A fresh router is returned on every call rather than a shared module-level
    one. That keeps a second mount — a second app in a test, or an app rebuilt
    during lifespan restart — from inheriting routes configured for a previous
    mount.

    Note when writing tests against this: FastAPI wraps an included router in an
    ``_IncludedRouter``, so ``app.routes`` does not list these paths directly.
    Enumerate them via ``app.openapi()["paths"]`` or
    ``route.original_router.routes``, not ``app.routes``.

    Args:
        store: Adapter to install. When ``None`` the current module-level store is
            left in place, which lets the app wire the store during lifespan
            startup and mount the router before it has one.

    Returns:
        A router ready for ``app.include_router``.
    """
    if store is not None:
        set_store(store)

    fresh = APIRouter(prefix="/api/v1/signals", tags=["signals"])
    fresh.get("/{symbol}/{timeframe}/latest")(latest)
    fresh.get("/{symbol}/{timeframe}/history")(history)
    fresh.get("/{symbol}/{timeframe}/range")(range_query)
    return fresh


def signal_to_response(signal: Signal) -> dict[str, Any]:
    """Serialise a signal for a response body.

    A named seam rather than an inline ``to_dict()`` so the API's output format
    has exactly one definition to change if it ever needs to.
    """
    return signal.to_dict()
