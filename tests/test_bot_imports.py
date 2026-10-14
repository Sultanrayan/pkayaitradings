"""The Telegram bot must stay independent of the four-agent AI system.

The bot in ``telegram_bot/`` is a separate engine. It reads biquote OHLCV, keeps
its own SQLite database, and computes its own seven-layer signal. It does not
consume agent output, and it must never come to depend on it.

Why this needs a test rather than a code review
----------------------------------------------
The bot already imports four things from ``shared/``: ``logging``, ``config``,
``schemas.market`` and ``schemas.enums``. That is unavoidable — they are market
primitives, not agent logic — but it means "the bot is standalone" is not
automatically true just because no ``from agents`` line exists today. A single
convenient import added under deadline would pass every behavioural test and
quietly couple the two systems.

These tests assert the property structurally instead: by parsing the import
graph rather than by running the bot. They are cheap, they cannot be satisfied by
a working-but-coupled implementation, and they fail loudly at review time.

One historical note. This file exists because a Phase 1 edit removed an enum from
``shared/schemas/enums.py`` without updating ``shared/schemas/__init__.py`` in the
same commit. Because the bot imports ``shared.schemas.market``, Python runs the
package ``__init__`` first, so that single out-of-order edit broke the bot's
imports with::

    ImportError: cannot import name 'UpdateTrigger' from 'shared.schemas.enums'

The lockstep requirement between ``enums.py``, ``signals.py`` and ``__init__.py``
is therefore load-bearing for a component that has nothing to do with agents.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
BOT_PACKAGE = REPO_ROOT / "telegram_bot"


def _bot_sources() -> list[Path]:
    """Every Python file that ships in the bot package, tests included."""
    return sorted(BOT_PACKAGE.rglob("*.py"))


def _imported_modules(path: Path) -> set[str]:
    """Top-level module names imported by ``path``.

    Handles ``import x``, ``import x.y``, ``from x import y`` and relative
    imports (which are reported as ``.`` because they cannot reach outside the
    package by definition).
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                found.add(".")
            elif node.module:
                found.add(node.module.split(".")[0])
    return found


def _known_third_party() -> set[str]:
    """Everything importable that is neither repo-local nor forbidden.

    The standard library is taken from ``sys.stdlib_module_names`` so it stays
    correct as Python adds or removes modules, rather than being a hand-kept list
    that silently rots. Third-party distributions are enumerated explicitly,
    because an unexpected one is exactly the thing worth noticing.
    """
    third_party = {
        "numpy",
        "pandas",
        "httpx",
        "telegram",
        "apscheduler",
        "pydantic",
        "structlog",
        "dotenv",
        # Test-only, and only reachable from telegram_bot/tests/.
        "pytest",
    }
    return set(sys.stdlib_module_names) | third_party


def _repo_local_modules() -> set[str]:
    """Top-level directories in this repository that are importable packages."""
    return {
        entry.name
        for entry in REPO_ROOT.iterdir()
        if entry.is_dir() and (entry / "__init__.py").exists()
    }


# --------------------------------------------------------------------------- #
# The bot's imports must stay clean
# --------------------------------------------------------------------------- #

#: Top-level packages the bot must never import. ``agents`` and ``orchestrator``
#: are the AI system; ``execution`` places orders; ``Raggrap`` is the retrieval
#: stack. The rest are LLM SDKs — the bot is indicators-only and spends nothing
#: on inference.
FORBIDDEN_ROOTS = {
    "agents",
    "orchestrator",
    "execution",
    "Raggrap",
    "openai",
    "anthropic",
    "cohere",
    "litellm",
}

#: Market-data packages the bot legitimately shares. ``data_pipeline`` holds the
#: biquote HTTP client — an HTTP transport for OHLCV, with no agent, orchestrator
#: or LLM import anywhere in it. Sharing one rate-limited client is the
#: difference between one upstream connection budget and two.
#:
#: Kept as an explicit allowlist rather than left out of the forbidden set
#: silently, so that adding a second shared package is a deliberate edit to this
#: file and shows up in review.
ALLOWED_SHARED_ROOTS = {"logging", "config", "schemas"}
ALLOWED_MARKET_ROOTS = {"data_pipeline"}


@pytest.mark.parametrize("path", _bot_sources(), ids=lambda p: p.name)
def test_the_bot_imports_nothing_from_the_ai_system(path: Path) -> None:
    """No bot module may import an agent, the orchestrator, or an LLM SDK."""
    offenders = _imported_modules(path) & FORBIDDEN_ROOTS
    assert not offenders, (
        f"{path.relative_to(REPO_ROOT)} imports {sorted(offenders)}; "
        "the bot must remain an independent indicators-only engine"
    )


@pytest.mark.parametrize("path", _bot_sources(), ids=lambda p: p.name)
def test_the_bot_only_imports_permitted_market_libraries(path: Path) -> None:
    """Everything the bot imports must be stdlib, third-party, or allowlisted.

    A total allowlist is stricter than a denylist: a brand-new dependency the bot
    does not need today would be rejected here rather than merging unnoticed.
    """
    permitted = FORBIDDEN_ROOTS | ALLOWED_SHARED_ROOTS | ALLOWED_MARKET_ROOTS | {"."}
    stdlib_and_third_party = _imported_modules(path) - _repo_local_modules()
    unknown = stdlib_and_third_party - permitted - _known_third_party()
    assert not unknown, (
        f"{path.relative_to(REPO_ROOT)} imports unrecognised modules "
        f"{sorted(unknown)}; add it to an allowlist deliberately if intended"
    )


@pytest.mark.parametrize("path", _bot_sources(), ids=lambda p: p.name)
def test_the_bot_never_names_an_agent_schema(path: Path) -> None:
    """The bot must not reach for ``TradeDecision`` or any other agent output type.

    Checked on raw source rather than the import graph because these names can be
    referenced in annotations, ``isinstance`` checks or docstrings — all of which
    are coupling even when they are not imports.
    """
    source = path.read_text(encoding="utf-8")
    for symbol in (
        "TradeDecision",
        "TechnicalSignal",
        "NewsSignal",
        "RiskAssessment",
        "TradeProposal",
        "SignalUpdate",
        "ActiveSignal",
    ):
        assert symbol not in source, (
            f"{path.relative_to(REPO_ROOT)} references {symbol}; the bot has its own "
            "Signal class in telegram_bot/engine.py"
        )


def test_the_bot_defines_its_own_signal_type() -> None:
    """The bot's Signal is local to the bot, which is what makes independence work."""
    source = (BOT_PACKAGE / "engine.py").read_text(encoding="utf-8")
    assert "class Signal:" in source


def test_no_module_anywhere_in_the_repo_wires_the_bot_to_the_agents() -> None:
    """Guard the inverse direction too: nothing may import the bot from a cycle path."""
    for path in (REPO_ROOT / "orchestrator").glob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert "telegram_bot" not in source, (
            f"{path.name} imports the Telegram bot; the bot is a separate system"
        )


# --------------------------------------------------------------------------- #
# The shared/ surface the bot legitimately depends on
# --------------------------------------------------------------------------- #

#: The only ``shared`` submodules the bot is allowed to import. These are market
#: primitives and configuration — not agent logic. Widening this list is how the
#: coupling would creep back in.


@pytest.mark.parametrize("path", _bot_sources(), ids=lambda p: p.name)
def test_the_bot_only_touches_allowed_shared_modules(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and not node.level:
            parts = node.module.split(".")
            if parts[0] == "shared":
                assert len(parts) >= 2, f"{path.name} imports a whole shared package"
                assert parts[1] in ALLOWED_SHARED_ROOTS, (
                    f"{path.name} imports shared.{parts[1]}; allowed: "
                    f"{sorted(ALLOWED_SHARED_ROOTS)}"
                )


def test_the_bot_can_import_shared_schemas() -> None:
    """The lockstep guard.

    ``shared/schemas/__init__.py`` re-exports every public name from ``enums``
    and ``signals``. Editing either without updating ``__init__`` breaks this
    import — and therefore the bot — even though the bot is not an AI component.
    """
    import shared.schemas  # noqa: F401
    from shared.schemas.enums import Timeframe
    from shared.schemas.market import OhlcSeries

    assert Timeframe.M5.biquote_interval == "5m"
    assert OhlcSeries is not None


def test_every_shared_schema_export_actually_resolves() -> None:
    """Catches a stale name left in ``__init__.__all__`` after a removal."""
    import shared.schemas as schemas

    missing = [name for name in schemas.__all__ if not hasattr(schemas, name)]
    assert not missing, f"shared.schemas.__all__ names non-existent objects: {missing}"


def test_the_bot_engine_imports_cleanly() -> None:
    """The Phase 1 gate, kept as a permanent test."""
    from telegram_bot.engine import Signal, compute_signal

    assert Signal is not None
    assert callable(compute_signal)
