"""Tests for the durable JSON-backed stores (users, access requests)."""

from __future__ import annotations

from pathlib import Path

from orchestrator.access import AccessRequestStore, RequestStatus
from orchestrator.auth import UserStore
from shared.persistence import read_json, write_json


def test_user_store_round_trips_through_disk(tmp_path: Path) -> None:
    path = tmp_path / "users.json"
    store = UserStore(path)
    user = store.register("Ada", "ada@example.com", "supersecret")
    assert user.verified is True
    assert store.authenticate("ada@example.com", "supersecret") is not None

    # A fresh store reads the same account back and can still authenticate.
    reloaded = UserStore(path)
    assert reloaded.size == 1
    restored = reloaded.get_by_email("ada@example.com")
    assert restored is not None
    assert restored.id == user.id
    assert restored.verified is True
    assert reloaded.authenticate("ada@example.com", "supersecret") is not None


def test_access_request_store_round_trips_through_disk(tmp_path: Path) -> None:
    path = tmp_path / "access_requests.json"
    store = AccessRequestStore(path)
    request = store.create(
        name="Dev", email="dev@example.com", use_case="Backtesting", website="https://x.dev"
    )
    store.approve(request.id, "token-123")

    reloaded = AccessRequestStore(path)
    restored = reloaded.get(request.id)
    assert restored is not None
    assert restored.status == RequestStatus.APPROVED
    assert restored.token == "token-123"
    assert restored.email == "dev@example.com"


def test_stores_are_in_memory_without_a_path() -> None:
    users = UserStore()
    users.register("Ada", "memory@example.com", "supersecret")
    assert users.size == 1  # nothing written to disk


def test_read_json_tolerates_missing_and_corrupt_files(tmp_path: Path) -> None:
    missing = tmp_path / "nope.json"
    assert read_json(missing) is None

    corrupt = tmp_path / "corrupt.json"
    corrupt.write_text("{not valid json", encoding="utf-8")
    assert read_json(corrupt) is None


def test_write_json_is_atomic_and_creates_directories(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "dir" / "data.json"
    write_json(target, {"a": 1})
    assert read_json(target) == {"a": 1}
    # No leftover temp files.
    assert [p.name for p in target.parent.iterdir()] == ["data.json"]
