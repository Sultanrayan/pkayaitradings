"""Phase 2B — the bot's own narrative fields and its broadcast gate.

The bot derives ``strength``, ``recommendation``, ``explanation``, ``risk_notes``
and ``invalidation`` from its own seven layers, its own ATR and its own swing
structure. It never receives them from the four-agent AI system, which has no
integration with it whatsoever. ``tests/test_bot_imports.py`` enforces that
structurally; these tests assert the derivation and the gate behave correctly.
"""

from __future__ import annotations

import pytest

from telegram_bot import narrative
from telegram_bot.defaults import BotConfig
from telegram_bot.engine import compute_signal
from telegram_bot.tests.conftest import make_trending_frame

NARRATIVE_FIELDS = ("recommendation", "explanation", "risk_notes", "invalidation")


def _permissive() -> BotConfig:
    import dataclasses

    from telegram_bot.db import Database
    from telegram_bot.defaults import seed_defaults

    db = Database(":memory:")
    db.initialise()
    seed_defaults(db)
    config = BotConfig.load(db)
    db.close()
    return dataclasses.replace(config, confidence_min=0.0)


# --------------------------------------------------------------------------- #
# Strength banding
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("confidence", "expected"),
    [
        (0.0, "WEAK"),
        (0.10, "WEAK"),
        (0.299, "WEAK"),
        (0.30, "MODERATE"),
        (0.50, "MODERATE"),
        (0.70, "MODERATE"),
        (0.701, "STRONG"),
        (1.0, "STRONG"),
    ],
)
def test_band_edges_match_the_specification(confidence: float, expected: str) -> None:
    assert narrative.band_strength(confidence) == expected


def test_banding_clamps_out_of_range_confidence() -> None:
    assert narrative.band_strength(-1.0) == "WEAK"
    assert narrative.band_strength(5.0) == "STRONG"


@pytest.mark.parametrize(
    ("strength", "size"), [("WEAK", 0.25), ("MODERATE", 0.60), ("STRONG", 1.00)]
)
def test_each_band_carries_a_size(strength: str, size: float) -> None:
    assert narrative.position_size_for(strength) == size


# --------------------------------------------------------------------------- #
# The four fields are populated on a real signal
# --------------------------------------------------------------------------- #


def test_a_real_signal_carries_all_five_narrative_fields() -> None:
    frame = make_trending_frame(300, seconds=300)
    signal = compute_signal(
        frame, symbol="XAUUSD", timeframe="5m", config=_permissive()
    )
    assert signal is not None

    for name in NARRATIVE_FIELDS:
        value = getattr(signal, name)
        assert value, f"{name} must never be empty on a real signal"
    assert signal.strength in {"WEAK", "MODERATE", "STRONG"}


def test_the_recommendation_names_the_direction_and_a_size() -> None:
    frame = make_trending_frame(300, seconds=300)
    signal = compute_signal(
        frame, symbol="XAUUSD", timeframe="5m", config=_permissive()
    )
    assert signal is not None
    side = "long" if signal.action == "BUY" else "short"
    assert side in signal.recommendation
    assert str(signal.strength) in signal.recommendation


def test_the_explanation_names_the_layers() -> None:
    """Derived from the bot's own layers, so it must mention them."""
    frame = make_trending_frame(300, seconds=300)
    signal = compute_signal(
        frame, symbol="XAUUSD", timeframe="5m", config=_permissive()
    )
    assert signal is not None
    lowered = signal.explanation.lower()
    for layer in ("trend", "momentum", "volume", "volatility"):
        assert layer in lowered, f"{layer} missing from the explanation"


def test_the_invalidation_names_the_bots_own_stop() -> None:
    frame = make_trending_frame(300, seconds=300)
    signal = compute_signal(
        frame, symbol="XAUUSD", timeframe="5m", config=_permissive()
    )
    assert signal is not None
    assert f"{signal.sl:.2f}" in signal.invalidation


def test_risk_notes_are_never_empty() -> None:
    """An empty section reads as an oversight; a clean bill is stated positively."""
    frame = make_trending_frame(300, seconds=300)
    signal = compute_signal(
        frame, symbol="XAUUSD", timeframe="5m", config=_permissive()
    )
    assert signal is not None
    assert signal.risk_notes


def test_invalidation_is_directional() -> None:
    """A long is cancelled below the stop; a short above it."""
    for up in (True, False):
        signal = compute_signal(
            make_trending_frame(300, seconds=300, up=up),
            symbol="XAUUSD",
            timeframe="5m",
            config=_permissive(),
        )
        assert signal is not None
        text = signal.invalidation.lower()
        if signal.action == "BUY":
            assert "below the stop" in text
        else:
            assert "above the stop" in text


def test_narrative_fields_are_persisted_in_the_record() -> None:
    """They must survive a restart, or a historical card renders empty."""
    frame = make_trending_frame(300, seconds=300)
    signal = compute_signal(
        frame, symbol="XAUUSD", timeframe="5m", config=_permissive()
    )
    assert signal is not None
    record = signal.to_record(sent_at=1)
    for name in ("strength", *NARRATIVE_FIELDS):
        assert record[name], f"{name} missing from the stored record"


def test_a_confluence_copy_keeps_the_narrative_fields() -> None:
    """`with_confluence` rebuilds the Signal; it must not drop the new fields."""
    frame = make_trending_frame(300, seconds=300)
    signal = compute_signal(
        frame, symbol="XAUUSD", timeframe="5m", config=_permissive()
    )
    assert signal is not None
    copy = signal.with_confluence(("5m", "15m"))
    assert copy.strength == signal.strength
    assert copy.explanation == signal.explanation
    assert copy.invalidation == signal.invalidation


# --------------------------------------------------------------------------- #
# The broadcast gate
# --------------------------------------------------------------------------- #


def test_the_gate_defaults_to_withholding_weak_signals() -> None:
    config = _permissive()
    assert config.broadcast_min_strength == "MODERATE"
    assert config.broadcast_min_confidence == 0.40
    assert config.passes_broadcast_gate("WEAK", 0.35) is False


@pytest.mark.parametrize(
    ("strength", "confidence", "expected"),
    [
        ("WEAK", 0.10, False),
        ("WEAK", 0.30, False),
        ("WEAK", 0.45, True),  # high confidence rescues a weak band
        ("MODERATE", 0.30, True),
        ("MODERATE", 0.50, True),
        ("STRONG", 0.80, True),
        ("", 0.10, False),  # unbanded, low confidence
    ],
)
def test_gate_outcomes(strength: str, confidence: float, expected: bool) -> None:
    assert _permissive().passes_broadcast_gate(strength, confidence) is expected


def test_the_gate_is_configurable_in_sqlite() -> None:
    """RULE 1: configuration lives in SQLite, not in code."""

    from telegram_bot.db import Database
    from telegram_bot.defaults import BotConfig, seed_defaults

    db = Database(":memory:")
    db.initialise()
    seed_defaults(db)
    assert BotConfig.load(db).broadcast_min_strength == "MODERATE"

    db.set_config("broadcast_min_strength", "STRONG")
    assert BotConfig.load(db).broadcast_min_strength == "STRONG"
    db.close()


def test_an_unrecognised_gate_band_does_not_silently_disable_delivery() -> None:
    """A typo in the config must not quietly stop every alert."""
    import dataclasses

    config = dataclasses.replace(_permissive(), broadcast_min_strength="BANANA")
    assert config.passes_broadcast_gate("WEAK", 0.10) is True


async def test_the_scanner_gates_a_weak_signal_without_storing_it_away(
    db, market
) -> None:
    """A gated signal is recorded and counted; only the message is withheld."""
    import dataclasses

    from telegram_bot.db import utcnow
    from telegram_bot.scanner import Scanner

    config = dataclasses.replace(
        _permissive(), broadcast_min_strength="STRONG", broadcast_min_confidence=0.99
    )
    market.set_frame("XAUUSD", "5m", make_trending_frame(300, seconds=300))
    scanner = Scanner(db=db, config=config, market=market, started_at=0.0)

    result = await scanner.scan(symbol="XAUUSD", timeframe="5m", now=utcnow())

    assert result.computed, "the signal should still be computed"
    assert result.stored, "a gated signal is still recorded"
    assert result.delivered == [], "but it must not be broadcast"
    assert result.gated, "and the reason must be recorded"
    assert db.signal_count_since(0) > 0


async def test_the_scanner_delivers_a_signal_that_clears_the_gate(db, market) -> None:
    import dataclasses

    from telegram_bot.db import utcnow
    from telegram_bot.scanner import Scanner

    config = dataclasses.replace(_permissive(), broadcast_min_strength="WEAK")
    market.set_frame("XAUUSD", "5m", make_trending_frame(300, seconds=300))
    scanner = Scanner(db=db, config=config, market=market, started_at=0.0)

    result = await scanner.scan(symbol="XAUUSD", timeframe="5m", now=utcnow())

    assert result.delivered, "a WEAK-allowed gate must let the signal through"
    assert not result.gated


# --------------------------------------------------------------------------- #
# Independence — restated per behaviour, not only structurally
# --------------------------------------------------------------------------- #


def test_the_narrative_module_imports_nothing_from_the_ai_system() -> None:
    """Checked on the parsed import graph, not on raw text.

    A text grep would fail on this module's own docstring, which names
    ``agents`` and ``orchestrator`` precisely to document that it does *not*
    import them. The interesting property is which modules are imported, so that
    is what is asserted.
    """
    import ast
    from pathlib import Path

    tree = ast.parse(Path(narrative.__file__).read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            imported.add(node.module.split(".")[0])

    forbidden = {"agents", "orchestrator", "execution", "openai", "anthropic"}
    assert not (imported & forbidden), (
        f"telegram_bot/narrative.py imports {sorted(imported & forbidden)}"
    )


def test_a_bot_signal_is_complete_without_any_agent_involvement() -> None:
    """The whole payload is derivable from the bot's own frame alone."""
    frame = make_trending_frame(300, seconds=300)
    signal = compute_signal(
        frame, symbol="XAUUSD", timeframe="5m", config=_permissive()
    )
    assert signal is not None
    for name in ("strength", *NARRATIVE_FIELDS):
        assert getattr(signal, name)
    assert signal.action in {"BUY", "SELL"}
    assert signal.risk_reward > 0
