"""Guard rails against losing user data on load, write or redeploy.

The risk these cover is specific and real: ``User`` gained the
``analysis_used_today`` / ``analysis_day_start`` fields when daily caps were
introduced. Every record already on the production volume predates them. If the
deserialiser could not read those records, ``UserStore._load`` used to skip them
and the next write persisted the shortened registry — silently, and irreversibly.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from orchestrator.auth import AuthError, UserStore, _deserialise_user

NOW = datetime(2026, 9, 1, tzinfo=UTC)

#: Exactly the shape written before daily caps existed: no analysis_used_today, no
#: analysis_day_start.
LEGACY_RECORD = {
    "id": "legacy1",
    "name": "Legacy User",
    "email": "legacy@example.com",
    "password_hash": None,
    "created_at": "2026-01-01T00:00:00+00:00",
    "provider": "password",
    "subject": None,
    "verified": True,
    "plan": "pro",
    "plan_expires_at": "2026-12-01T00:00:00+00:00",
    "analysis_used": 17,
    "analysis_period_start": "2026-09-01T00:00:00+00:00",
}


def _write(path: Path, records: list[dict]) -> None:
    path.write_text(json.dumps(records, indent=2), encoding="utf-8")


# ------------------------------------------------------- backward compatible


def test_legacy_record_deserialises() -> None:
    user = _deserialise_user(LEGACY_RECORD)
    assert user is not None
    assert user.id == "legacy1"
    assert user.email == "legacy@example.com"
    assert user.plan == "pro"
    assert user.analysis_used == 17


def test_missing_daily_fields_default_rather_than_fail() -> None:
    user = _deserialise_user(LEGACY_RECORD)
    assert user is not None
    assert user.analysis_used_today == 0
    assert isinstance(user.analysis_day_start, datetime)
    assert user.analysis_day_start.tzinfo is not None


def test_store_loading_legacy_file_preserves_the_account(tmp_path: Path) -> None:
    path = tmp_path / "users.json"
    _write(path, [LEGACY_RECORD])
    store = UserStore(path)
    assert store.size == 1
    user = store.get_by_email("legacy@example.com")
    assert user is not None
    assert user.analysis_used == 17
    assert store._unreadable == []


def test_legacy_pro_user_is_not_demoted_on_load(tmp_path: Path) -> None:
    """A Pro record written before this change must survive intact."""
    path = tmp_path / "users.json"
    _write(path, [LEGACY_RECORD])
    store = UserStore(path)
    user = store.get_by_email("legacy@example.com")
    assert user is not None
    assert user.plan == "pro"
    assert user.plan_expires_at is not None


# ----------------------------------------------------- unreadable rows


def _corrupt(path: Path, extra: dict) -> None:
    _write(path, [LEGACY_RECORD, extra])


def test_unreadable_row_is_not_silently_dropped(tmp_path: Path) -> None:
    path = tmp_path / "users.json"
    # No "id" at all: the deserialiser cannot rebuild this row.
    _corrupt(path, {"name": "No Id", "email": "noid@example.com"})
    store = UserStore(path)
    assert store.size == 1
    assert len(store._unreadable) == 1


def test_unreadable_row_blocks_the_write_that_would_drop_it(tmp_path: Path) -> None:
    path = tmp_path / "users.json"
    _corrupt(path, {"name": "No Id", "email": "noid@example.com"})
    store = UserStore(path)

    with pytest.raises(AuthError, match="could not be read"):
        store._persist()

    # The file on disk is untouched, so the row can still be recovered by hand.
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert len(on_disk) == 2
    assert any(r.get("email") == "noid@example.com" for r in on_disk)


def test_registration_is_refused_while_a_row_is_unreadable(tmp_path: Path) -> None:
    """The store must not accept writes that would persist the shortened registry."""
    path = tmp_path / "users.json"
    _corrupt(path, {"name": "No Id", "email": "noid@example.com"})
    store = UserStore(path)
    with pytest.raises(AuthError, match="refusing to write"):
        store.register("New", "new@example.com", "supersecret")


def test_a_non_dict_row_is_also_quarantined(tmp_path: Path) -> None:
    path = tmp_path / "users.json"
    path.write_text(json.dumps([LEGACY_RECORD, "garbage"]), encoding="utf-8")
    store = UserStore(path)
    assert store.size == 1
    assert len(store._unreadable) == 1
    with pytest.raises(AuthError):
        store._persist()


def test_a_clean_store_persists_normally(tmp_path: Path) -> None:
    path = tmp_path / "users.json"
    _write(path, [LEGACY_RECORD])
    store = UserStore(path)
    store.register("Second", "second@example.com", "supersecret")
    assert store.size == 2
    reloaded = UserStore(path)
    assert reloaded.size == 2
    assert reloaded._unreadable == []


def test_assert_intact_is_quiet_when_clean(tmp_path: Path) -> None:
    path = tmp_path / "users.json"
    _write(path, [LEGACY_RECORD])
    store = UserStore(path)
    store.assert_intact()  # must not raise


def test_empty_file_is_not_treated_as_corruption(tmp_path: Path) -> None:
    path = tmp_path / "users.json"
    path.write_text("[]", encoding="utf-8")
    store = UserStore(path)
    assert store.size == 0
    assert store._unreadable == []
    store._persist()  # must not raise


# ------------------------------------------------------------- round trip


def test_round_trip_adds_the_new_fields_without_losing_the_old(tmp_path: Path) -> None:
    path = tmp_path / "users.json"
    _write(path, [LEGACY_RECORD])
    store = UserStore(path)
    user = store.get_by_email("legacy@example.com")
    assert user is not None
    # User is frozen, so the update goes through replace() as the API layer does.
    store.update(replace(user, analysis_used_today=3))

    reloaded = UserStore(path).get_by_email("legacy@example.com")
    assert reloaded is not None
    assert reloaded.analysis_used == 17
    assert reloaded.plan == "pro"
    assert reloaded.analysis_used_today == 3
    # The upgrade added fields; it must not have dropped any.
    for key in ("id", "name", "email", "created_at", "plan", "plan_expires_at"):
        assert key in json.loads(path.read_text(encoding="utf-8"))[0]


def test_new_field_defaults_do_not_leak_into_older_records(tmp_path: Path) -> None:
    """Reading a legacy record must not mutate the file on disk."""
    path = tmp_path / "users.json"
    _write(path, [LEGACY_RECORD])
    before = json.loads(path.read_text(encoding="utf-8"))
    UserStore(path)
    after = json.loads(path.read_text(encoding="utf-8"))
    assert before == after


def test_user_field_order_is_irrelevant() -> None:
    reordered = {k: LEGACY_RECORD[k] for k in reversed(list(LEGACY_RECORD))}
    assert _deserialise_user(reordered) is not None


def test_a_record_missing_analysis_used_still_loads() -> None:
    minimal = {
        "id": "m1",
        "name": "M",
        "email": "m@example.com",
        "password_hash": None,
    }
    user = _deserialise_user(minimal)
    assert user is not None
    assert user.analysis_used == 0
    assert user.plan == "free"
