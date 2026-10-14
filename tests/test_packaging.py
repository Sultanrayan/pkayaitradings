"""Guard the explicit setuptools package list against the tree on disk.

``[tool.setuptools] packages`` is an explicit list, so a new package directory
that nobody adds to it fails the Docker build with
``package directory 'X' does not exist`` — the same failure ``Raggrap`` caused.
This check makes the omission a test failure instead.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
# Directories whose Python subpackages are not shipped as importable packages.
# These names are pruned at *any* depth, not just at the top level: a package that
# contains its own `tests/` directory (e.g. `signals/tests`) would otherwise be
# reported as an undeclared package and fail this guard.
_EXCLUDED = {"tests", "scripts", "migrations", "deploy", "monitoring", "Research"}
# Never descend into these: virtualenvs and build output contain thousands of
# site-packages that are obviously not ours to declare.
_PRUNED = {
    ".venv",
    "venv",
    "site-packages",
    "node_modules",
    "__pycache__",
    ".next",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "build",
    "dist",
}


def _declared_packages() -> set[str]:
    with (_ROOT / "pyproject.toml").open("rb") as handle:
        data = tomllib.load(handle)
    return set(data["tool"]["setuptools"]["packages"])


def _packages_on_disk() -> set[str]:
    """Every importable package directory in the tree, excluding vendored trees."""
    found: set[str] = set()
    for top in sorted(p for p in _ROOT.iterdir() if p.is_dir()):
        if top.name in _EXCLUDED or top.name in _PRUNED or top.name.startswith("."):
            continue
        if not (top / "__init__.py").exists():
            continue
        found.add(top.name)
        # os.walk with in-place pruning: rglob would still descend into
        # Raggrap/.venv and report its entire site-packages.
        for dirpath, dirnames, _filenames in os.walk(top):
            dirnames[:] = [
                name
                for name in sorted(dirnames)
                if name not in _PRUNED
                and name not in _EXCLUDED
                and not name.startswith((".", "__"))
            ]
            for name in dirnames:
                if not (Path(dirpath) / name / "__init__.py").exists():
                    continue
                relative = (Path(dirpath) / name).relative_to(_ROOT)
                found.add(str(relative).replace("\\", "."))
    return found


def test_declared_packages_exist_on_disk() -> None:
    """Every declared package must be a real directory."""
    missing = sorted(
        name for name in _declared_packages() if not (_ROOT / Path(*name.split("."))).is_dir()
    )
    assert missing == [], f"pyproject declares packages that do not exist: {missing}"


def test_new_packages_are_declared() -> None:
    """Every importable package on disk must be declared, or the build breaks."""
    undeclared = sorted(_packages_on_disk() - _declared_packages())
    assert undeclared == [], (
        "packages present on disk but missing from [tool.setuptools] packages; "
        "the Docker build will fail with \"package directory ... does not exist\": "
        f"{undeclared[:20]}" + (f" (+{len(undeclared) - 20} more)" if len(undeclared) > 20 else "")
    )
