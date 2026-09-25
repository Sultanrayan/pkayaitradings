"""Tiny atomic JSON file helpers for durable process-local stores.

The auth user registry and the developer access-request store use these to
survive restarts when a ``DATA_DIR`` is configured (production mounts a volume
there). Writes go to a temporary file first and are then replaced atomically, so
a crash mid-write never corrupts the store.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from shared.logging import get_logger

_logger = get_logger(__name__)


def read_json(path: Path) -> Any | None:
    """Read JSON from ``path``, returning ``None`` when it does not exist.

    A corrupt file is logged and treated as absent rather than raising, so a bad
    write never takes the process down on boot.
    """
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        _logger.warning("persistence.read_failed", path=str(path), error=repr(exc))
        return None


def write_json(path: Path, payload: Any) -> None:
    """Atomically write ``payload`` as JSON to ``path`` (creating directories)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, separators=(",", ":"), default=str)
                handle.flush()
                os.fsync(handle.fileno())
            Path(tmp_name).replace(path)
        except BaseException:
            with_cleanup = Path(tmp_name)
            if with_cleanup.exists():
                with_cleanup.unlink(missing_ok=True)
            raise
    except OSError as exc:
        _logger.warning("persistence.write_failed", path=str(path), error=repr(exc))
