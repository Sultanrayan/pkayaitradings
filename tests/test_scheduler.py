"""Tests for the Celery scheduler wiring.

The Celery app is imported for its configuration and task registry; no broker
connection is opened, because nothing here calls ``.delay()`` or ``.apply_async()``.
"""

from __future__ import annotations

from typing import Any

from orchestrator import scheduler as sched
from shared.config import Settings


def make_settings(**overrides: Any) -> Settings:
    base: dict[str, Any] = {
        "environment": "development",
        "llm_provider": "none",
        "trading_symbols": ["XAUUSD"],
        "analysis_interval_seconds": 300,
    }
    base.update(overrides)
    return Settings(**base)


# --------------------------------------------------------------------------- #
# Registered tasks
# --------------------------------------------------------------------------- #


def test_analysis_task_is_still_registered() -> None:
    assert "orchestrator.scheduler.analyze_all_symbols" in sched.celery_app.tasks


def test_compute_signals_task_is_still_registered() -> None:
    """The bar-anchored engine is a separate subsystem and must survive.

    It is easy to conflate this with the removed Signal Updater because both
    emitted a "signal". This test pins that the engine task is still wired.
    """
    assert "orchestrator.scheduler.compute_signals" in sched.celery_app.tasks


# --------------------------------------------------------------------------- #
# The Signal Updater is gone
# --------------------------------------------------------------------------- #


def test_the_signal_updater_task_is_unregistered() -> None:
    assert "orchestrator.scheduler.update_active_signals" not in sched.celery_app.tasks


def test_the_signal_updater_helper_is_removed() -> None:
    assert not hasattr(sched, "_run_signal_updates")


def test_no_signal_update_settings_remain() -> None:
    """The 13 removed settings must not linger on Settings.

    Asserted by attribute rather than by grep so a reintroduced setting with a
    different name still shows up in the diff review.
    """
    fields = Settings.model_fields
    leftovers = [name for name in fields if name.startswith("signal_update")]
    assert not leftovers, f"signal_update settings still present: {leftovers}"


def test_the_signal_engine_settings_are_untouched() -> None:
    """The removal must not have taken the signal engine's settings with it."""
    fields = Settings.model_fields
    for name in (
        "signal_engine_enabled",
        "signal_engine_mode",
        "signal_engine_interval_seconds",
        "signal_engine_min_bars_between_signals",
        "signal_engine_lookback",
    ):
        assert name in fields, f"{name} was removed along with the Signal Updater"


# --------------------------------------------------------------------------- #
# Beat schedule
# --------------------------------------------------------------------------- #


def test_beat_schedule_has_exactly_two_entries() -> None:
    """``analyze-all-symbols`` and ``compute-signals``. Nothing else.

    The removed third entry was the Signal Updater. ``compute-signals`` is the
    bar-anchored engine and is NOT the updater — it must remain.
    """
    beat = sched.celery_app.conf.beat_schedule
    assert set(beat) == {"analyze-all-symbols", "compute-signals"}
    assert beat["analyze-all-symbols"]["task"] == (
        "orchestrator.scheduler.analyze_all_symbols"
    )
    assert beat["compute-signals"]["task"] == "orchestrator.scheduler.compute_signals"


def test_the_removed_beat_entry_is_gone() -> None:
    assert "update-active-signals" not in sched.celery_app.conf.beat_schedule


def test_beat_schedule_intervals_are_numeric() -> None:
    """Celery rejects a non-numeric schedule outright."""
    for entry in sched.celery_app.conf.beat_schedule.values():
        assert isinstance(entry["schedule"], float)
        assert entry["schedule"] > 0
