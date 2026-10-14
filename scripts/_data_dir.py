"""Resolve the live data directory for operator scripts.

Why this exists
---------------
``DATA_DIR`` is ``/data``, which is the path **inside the container**. On the host
that path usually does not exist, so a script run directly on the server would
resolve it, find nothing, and quietly exit — an operator would reasonably conclude
the migration had run when it had not touched a single record.

Two correct invocations, both supported:

    docker compose -f docker-compose.prod.yml --env-file .env.production \\
        exec api python scripts/migrate_trial_pro_to_one_week.py --dry-run

    python scripts/migrate_trial_pro_to_one_week.py \\
        --data-dir "$(docker volume inspect -f '{{.Mountpoint}}' pkay-tdai_pkay_data)"

:func:`resolve` refuses to return a directory that does not exist, and explains the
two options above rather than letting the caller proceed against a wrong path.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

VOLUME = os.environ.get("PKAY_DATA_VOLUME", "pkay-tdai_pkay_data")

REQUIRED_FILES = ("users.json",)

_MOUNTPOINT_HINT = (
    f'docker volume inspect -f "{{{{.Mountpoint}}}}" {VOLUME}'
)


def _volume_mountpoint() -> str | None:
    """Host path of the data volume, if Docker can tell us."""
    try:
        result = subprocess.run(
            ["docker", "volume", "inspect", "-f", "{{.Mountpoint}}", VOLUME],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    path = result.stdout.strip()
    return path or None


def resolve(explicit: str | None) -> Path:
    """Return a data directory that exists, or exit with guidance."""
    if explicit:
        path = Path(explicit)
        if not path.is_dir():
            _fail(f"--data-dir {path} is not a directory on this machine.")
        return path

    configured = os.environ.get("DATA_DIR", "").strip()
    if configured and Path(configured).is_dir():
        return Path(configured)

    mountpoint = _volume_mountpoint()
    if mountpoint and Path(mountpoint).is_dir():
        return Path(mountpoint)

    _fail(
        "Could not find the data directory.\n"
        f"  DATA_DIR is {configured or '(unset)'!r}, which is the container path and does "
        "not exist on the host.\n"
        "Run the script inside the API container:\n"
        "  docker compose -f docker-compose.prod.yml --env-file .env.production \\\n"
        "      exec api python scripts/<this-script>.py --dry-run\n"
        "or point it at the volume's host path:\n"
        f"  --data-dir \"{_MOUNTPOINT_HINT}\""
    )
    raise AssertionError("unreachable")  # pragma: no cover


def assert_present(base: Path) -> None:
    """Fail before any write if the expected stores are missing."""
    missing = [name for name in REQUIRED_FILES if not (base / name).exists()]
    if missing:
        _fail(
            f"{base} does not contain {', '.join(missing)}.\n"
            "This does not look like the production data volume. Refusing to write."
        )


def _fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(2)
