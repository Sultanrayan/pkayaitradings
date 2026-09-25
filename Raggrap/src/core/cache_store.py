"""Cache adapters with Redis and in-memory fallback."""

from __future__ import annotations

import contextlib
import time
from typing import Any, Protocol, cast

from ..models.schemas import QueryResponse


class CacheBackend(Protocol):
    """Low-level key/value cache with TTL semantics."""

    def get(self, key: str) -> str | None: ...

    def setex(self, key: str, ttl: int, value: str) -> None: ...

    def delete(self, key: str) -> None: ...

    def flush(self) -> None: ...

    def close(self) -> None: ...


class InMemoryCacheBackend:
    def __init__(self) -> None:
        self._store: dict[str, tuple[str, float | None]] = {}

    def get(self, key: str) -> str | None:
        item = self._store.get(key)
        if item is None:
            return None
        value, expires_at = item
        if expires_at is not None and time.time() > expires_at:
            self._store.pop(key, None)
            return None
        return value

    def setex(self, key: str, ttl: int, value: str) -> None:
        expires_at = time.time() + ttl if ttl > 0 else None
        self._store[key] = (value, expires_at)

    def delete(self, key: str) -> None:
        self._store.pop(key, None)

    def flush(self) -> None:
        self._store.clear()

    def close(self) -> None:
        return None


class RedisCacheBackend:
    def __init__(self, client: Any) -> None:
        self._client = client

    def get(self, key: str) -> str | None:
        return cast(str | None, self._client.get(key))

    def setex(self, key: str, ttl: int, value: str) -> None:
        self._client.setex(key, ttl, value)

    def delete(self, key: str) -> None:
        self._client.delete(key)

    def flush(self) -> None:
        self._client.flushdb()

    def close(self) -> None:
        with contextlib.suppress(Exception):
            self._client.close()


class CacheStore:
    """Session-aware cache wrapper used by the engine.

    Serialises :class:`QueryResponse` values to JSON and stores them under the
    caller-provided key. When ``enable_cache`` is false reads always miss and
    writes are no-ops so the store never grows.
    """

    def __init__(self, settings: Any, backend: CacheBackend | None = None) -> None:
        self._backend = backend or create_cache_backend(settings)
        self._disabled = not settings.enable_cache

    def get(self, key: str) -> QueryResponse | None:
        if self._disabled:
            return None
        raw = self._backend.get(key)
        if raw is None:
            return None
        try:
            return QueryResponse.model_validate_json(raw)
        except Exception:
            return None

    def setex(self, key: str, ttl: int, value: QueryResponse) -> None:
        if self._disabled:
            return
        self._backend.setex(key, ttl, value.model_dump_json())

    def delete(self, key: str) -> None:
        self._backend.delete(key)

    def flush(self) -> None:
        self._backend.flush()

    def close(self) -> None:
        self._backend.close()


def create_cache_backend(settings: Any) -> CacheBackend:
    """Choose the in-memory or Redis backend based on configuration."""
    host = settings.redis_host
    if not host:
        return InMemoryCacheBackend()
    try:
        # Fast fail: probe TCP reachability with a short timeout before handing
        # the connection to redis-py, whose ping() can block for far longer when
        # nothing is listening (common on localhost dev machines).
        import socket

        with socket.create_connection((host, settings.redis_port), timeout=0.5):
            pass
    except Exception:
        return InMemoryCacheBackend()
    try:
        import redis

        client = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            db=settings.redis_db,
            password=settings.redis_password or None,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        client.ping()
        return RedisCacheBackend(client)
    except Exception:
        return InMemoryCacheBackend()


def create_cache_store(settings: Any) -> CacheStore:
    return CacheStore(settings)
