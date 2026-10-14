"""The operator scripts must never quietly target the wrong path.

``DATA_DIR`` is ``/data``, which is the path inside the container. On the host that
path does not exist, so a script that resolved it and found nothing would exit 0-ish
and the operator would believe a migration had run when it had touched nothing.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from scripts import _data_dir


def test_explicit_missing_dir_fails_loudly(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exc:
        _data_dir.resolve(str(tmp_path / "nope"))
    assert exc.value.code == 2


def test_explicit_existing_dir_is_returned(tmp_path: Path) -> None:
    assert _data_dir.resolve(str(tmp_path)) == tmp_path


def test_container_path_is_not_accepted_on_the_host(monkeypatch, tmp_path: Path) -> None:
    """DATA_DIR=/data must not resolve to a fresh empty directory here."""
    monkeypatch.setattr(_data_dir, "_volume_mountpoint", lambda: None)
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "definitely-not-here"))
    with pytest.raises(SystemExit) as exc:
        _data_dir.resolve(None)
    assert exc.value.code == 2


def test_volume_mountpoint_is_preferred_over_a_stale_data_dir(monkeypatch, tmp_path: Path) -> None:
    """When DATA_DIR points nowhere, the Docker volume is the right answer."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "gone"))
    monkeypatch.setattr(_data_dir, "_volume_mountpoint", lambda: str(tmp_path))
    assert _data_dir.resolve(None) == tmp_path


def test_mountpoint_probe_survives_a_missing_docker(monkeypatch) -> None:
    def boom(*_args, **_kwargs):
        raise OSError("no docker here")

    monkeypatch.setattr(subprocess, "run", boom)
    assert _data_dir._volume_mountpoint() is None


def test_mountpoint_probe_returns_none_on_failure(monkeypatch) -> None:
    class Result:
        returncode = 1
        stdout = ""

    monkeypatch.setattr(subprocess, "run", lambda *_a, **_k: Result())
    assert _data_dir._volume_mountpoint() is None


def test_mountpoint_probe_reads_the_path(monkeypatch) -> None:
    class Result:
        returncode = 0
        stdout = "/var/lib/docker/volumes/x/_data\n"

    monkeypatch.setattr(subprocess, "run", lambda *_a, **_k: Result())
    assert _data_dir._volume_mountpoint() == "/var/lib/docker/volumes/x/_data"


def test_missing_users_json_is_refused(tmp_path: Path) -> None:
    """Pointing at the wrong directory must fail before anything is written."""
    (tmp_path / "something-else.json").write_text("[]", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        _data_dir.assert_present(tmp_path)
    assert exc.value.code == 2


def test_present_users_json_passes(tmp_path: Path) -> None:
    (tmp_path / "users.json").write_text("[]", encoding="utf-8")
    _data_dir.assert_present(tmp_path)


# ------------------------------------------------ the migration guards its write


def test_migration_refuses_without_the_store(tmp_path: Path, capsys) -> None:
    from scripts.migrate_trial_pro_to_one_week import main

    argv = ["migrate", "--data-dir", str(tmp_path), "--apply", "--yes"]
    old = __import__("sys").argv
    __import__("sys").argv = argv
    try:
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 2
    finally:
        __import__("sys").argv = old


def test_migration_dry_run_writes_nothing(tmp_path: Path) -> None:
    from scripts.migrate_trial_pro_to_one_week import main

    legacy = {
        "id": "u1",
        "email": "t@example.com",
        "plan": "pro",
        "plan_expires_at": "2026-12-01T00:00:00+00:00",
    }
    users_path = tmp_path / "users.json"
    users_path.write_text(json.dumps([legacy]), encoding="utf-8")
    (tmp_path / "billing_payments.json").write_text("[]", encoding="utf-8")
    before = users_path.read_text(encoding="utf-8")

    old = __import__("sys").argv
    __import__("sys").argv = ["migrate", "--data-dir", str(tmp_path), "--dry-run"]
    try:
        assert main() == 0
    finally:
        __import__("sys").argv = old

    assert users_path.read_text(encoding="utf-8") == before


def test_migration_apply_backs_up_before_writing(tmp_path: Path) -> None:
    from scripts.migrate_trial_pro_to_one_week import main

    legacy = {
        "id": "u1",
        "email": "t@example.com",
        "plan": "pro",
        "plan_expires_at": "2026-12-01T00:00:00+00:00",
    }
    users_path = tmp_path / "users.json"
    users_path.write_text(json.dumps([legacy]), encoding="utf-8")
    (tmp_path / "billing_payments.json").write_text("[]", encoding="utf-8")

    old = __import__("sys").argv
    __import__("sys").argv = ["migrate", "--data-dir", str(tmp_path), "--apply", "--yes"]
    try:
        assert main() == 0
    finally:
        __import__("sys").argv = old

    backups = list(tmp_path.glob("users.json.bak-*"))
    assert len(backups) == 1
    # The backup must contain the pre-migration value.
    assert json.loads(backups[0].read_text(encoding="utf-8"))[0]["plan_expires_at"].startswith("2026-12-01")
    # And the live file must now be inside the one-week window.
    assert json.loads(users_path.read_text(encoding="utf-8"))[0]["plan_expires_at"] != "2026-12-01T00:00:00+00:00"
