"""Tests for the per-cycle report parser.

The parser is what the 24h window judgement rests on, and the two earlier
monitoring scripts both produced confident wrong answers — one reported
phantom 429s by matching digits inside Celery task UUIDs, the other reported
phantom missing-usage events by matching the dotted event name against the
underscored field on an unrelated line. These tests pin the behaviours that
prevent a repeat: fields are read from the parsed dict, cumulative counters are
differenced, and a worker restart re-bases instead of producing a spike.
"""

from __future__ import annotations

import importlib.util
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

_ROOT = Path(__file__).resolve().parents[1]


def _load_report_module() -> Any:
    """Import deploy/report_24h.py by path; deploy/ is not an importable package."""
    path = _ROOT / "deploy" / "report_24h.py"
    spec = importlib.util.spec_from_file_location("report_24h", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


report = _load_report_module()


def _cycle_line(
    *,
    symbol: str = "XAUUSD",
    calls: int = 7,
    prompt: int = 1775,
    completion: int = 1094,
    rate_limited: int = 0,
    failures: int = 0,
    usage_missing: int = 0,
    timestamp: str = "2026-10-02T08:54:02.633744Z",
) -> str:
    """One worker log line shaped exactly like the real ``cycle_complete`` output."""
    total = prompt + completion
    return (
        f"worker-1  | [2026-10-02 08:54:02,633: INFO/ForkPoolWorker-2] "
        f"{{'symbol': '{symbol}', 'decision': 'SKIP', 'score': 0.0, "
        f"'traded': False, 'correlation_id': 'abc123', "
        f"'llm_calls': {calls}, 'llm_attempts': {calls}, 'llm_retries': 0, "
        f"'llm_rate_limited': {rate_limited}, 'llm_timeouts': 0, "
        f"'llm_budget_exhausted': 0, 'llm_failures': {failures}, "
        f"'llm_prompt_tokens': {prompt}, 'llm_completion_tokens': {completion}, "
        f"'llm_cached_tokens': 0, 'llm_total_tokens': {total}, "
        f"'llm_usage_missing': {usage_missing}, "
        f"'llm_cost_units': {(prompt + completion) * 4}, 'llm_cost_usd': 0.000459, "
        f"'llm_cache_hit_rate': 0.0, 'event': 'pipeline.cycle_complete', "
        f"'level': 'info', 'logger': 'orchestrator.pipeline', "
        f"'timestamp': '{timestamp}'}}"
    )


def _task_line(seconds: float = 71.83) -> str:
    return (
        "worker-1  | [2026-10-02 08:54:38,603: INFO/ForkPoolWorker-2] "
        "Task orchestrator.scheduler.analyze_all_symbols"
        "[01bca656-5774-4e9b-8daf-a384449c2f42] succeeded in "
        f"{seconds}s: None"
    )


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #


def test_parse_event_extracts_the_dict() -> None:
    event = report.parse_event(_cycle_line())
    assert event is not None
    assert event["symbol"] == "XAUUSD"
    assert event["event"] == "pipeline.cycle_complete"


def test_parse_event_ignores_a_plain_log_line() -> None:
    """Celery's own lines carry no dict and must not be mistaken for events."""
    assert report.parse_event("worker-1 | Scheduler: Sending due task foo") is None


def test_parse_event_survives_a_truncated_line() -> None:
    """A cut-off line raises SyntaxError from literal_eval; that must be None."""
    assert report.parse_event("worker-1 | {'symbol': 'XAUUSD', 'calls': ") is None


# --------------------------------------------------------------------------- #
# Phantom-grep regressions
# --------------------------------------------------------------------------- #


def test_task_uuid_digits_are_not_rate_limits() -> None:
    """Regression: a UUID containing '429' must not read as a rate limit.

    The first monitoring script grepped the bare string ``429`` and reported two
    rate limits on a worker that had made zero LLM calls. Every digit run in a
    Celery task UUID matched.
    """
    line = (
        "worker-1  | [2026-10-02 07:28:24,262: INFO/MainProcess] Task "
        "orchestrator.scheduler.update_active_signals"
        "[82c14294-9925-4a2a-b630-266177938d17] received"
    )
    assert "429" in line
    events = list(report.iter_events([line]))
    assert events == []
    counts = report._count_events(events)
    assert counts.get("pipeline.cycle_complete", 0) == 0


def test_usage_missing_event_is_not_matched_by_the_field_name() -> None:
    """Regression: ``llm.usage_missing`` vs the ``llm_usage_missing`` field.

    The second script grepped the dotted event name, which regex-matched the
    underscored field on every cycle line and reported missing usage on a cycle
    that reported ``llm_usage_missing: 0``.
    """
    line = _cycle_line(usage_missing=0)
    assert "llm.usage_missing" not in line  # the field is underscored here
    counts = report._count_events(list(report.iter_events([line])))
    assert counts.get("llm.usage_missing", 0) == 0

    # A genuine missing-usage warning does carry the dotted event name.
    warning = (
        "worker-1  | [2026-10-02 08:54:02,633: WARNING/ForkPoolWorker-2] "
        "{'model': 'claude-opus-4-8', 'event': 'llm.usage_missing', 'level': 'warning'}"
    )
    warned = report._count_events(list(report.iter_events([warning])))
    assert warned.get("llm.usage_missing") == 1


# --------------------------------------------------------------------------- #
# Cumulative counters are differenced
# --------------------------------------------------------------------------- #


def test_second_symbol_is_differenced_not_summed() -> None:
    """Counters are cumulative per process, so the second symbol is a delta.

    This is the whole reason the report differences: BTCUSD's line carries the
    cycle total, not BTCUSD's own spend.
    """
    lines = [
        _cycle_line(symbol="XAUUSD", calls=7, prompt=1775, completion=1094),
        _cycle_line(symbol="BTCUSD", calls=14, prompt=3550, completion=2188),
    ]
    cycles = report.derive_cycles(list(report.iter_events(lines)))

    assert [c.symbol for c in cycles] == ["XAUUSD", "BTCUSD"]
    assert cycles[0].counters["llm_calls"] == 7
    assert cycles[1].counters["llm_calls"] == 7  # 14 - 7, not 14
    # Cumulative total 5738 less the first cycle's 2869. Taking the absolute
    # value would have reported BTCUSD as nearly double what it actually cost.
    assert cycles[1].counters["llm_total_tokens"] == 2869
    assert cycles[1].counters["llm_prompt_tokens"] == 1775
    assert cycles[1].counters["llm_completion_tokens"] == 1094


def test_worker_restart_rebases_instead_of_spiking() -> None:
    """A counter going backwards means the process restarted; re-base, do not subtract."""
    lines = [
        _cycle_line(symbol="XAUUSD", calls=7, prompt=1775, completion=1094),
        # Worker restarted: counters are back near zero.
        _cycle_line(symbol="XAUUSD", calls=6, prompt=1500, completion=1000),
    ]
    cycles = report.derive_cycles(list(report.iter_events(lines)))

    assert cycles[1].worker_epoch == 2
    assert cycles[1].counters["llm_calls"] == 6
    assert cycles[1].counters["llm_total_tokens"] == 2500
    assert min(c.counters["llm_calls"] for c in cycles) > 0


def test_first_cycle_of_an_epoch_is_not_a_leftover() -> None:
    """The first line after a restart is that symbol's own work, not a remainder."""
    lines = [_cycle_line(symbol="XAUUSD", calls=7, prompt=1775, completion=1094)]
    cycles = report.derive_cycles(list(report.iter_events(lines)))
    assert cycles[0].worker_epoch == 1
    assert cycles[0].counters["llm_calls"] == 7


def test_non_cycle_events_are_not_treated_as_cycles() -> None:
    """Only pipeline.cycle_complete becomes a cycle."""
    lines = [
        _task_line(),
        "worker-1 | {'event': 'llm.usage', 'prompt_tokens': 616}",
        _cycle_line(),
    ]
    cycles = report.derive_cycles(list(report.iter_events(lines)))
    assert len(cycles) == 1


# --------------------------------------------------------------------------- #
# Statistics
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("values", "expected_median"),
    [
        ([1.0], 1.0),
        ([1.0, 3.0], 2.0),
        ([1.0, 2.0, 3.0], 2.0),
        ([1.0, 2.0, 3.0, 4.0], 2.5),
        ([10.0, 10.0, 10.0], 10.0),
    ],
)
def test_median(values: list[float], expected_median: float) -> None:
    assert report.median(values) == pytest.approx(expected_median)


def test_percentile_of_empty_input_is_zero_not_an_error() -> None:
    assert report.percentile([], 0.95) == 0.0
    assert report.median([]) == 0.0


def test_p95_sits_above_the_median_for_a_skewed_series() -> None:
    values = [10.0] * 19 + [500.0]
    assert report.percentile(values, 0.95) > report.median(values)
    assert report.percentile(values, 0.95) <= max(values)


def test_cost_usd_is_derived_from_units_not_the_rounded_field() -> None:
    """cost_usd is logged at 6dp; the report recovers precision from cost_units."""
    lines = [_cycle_line(prompt=1775, completion=1094)]
    cycles = report.derive_cycles(list(report.iter_events(lines)))
    assert cycles[0].cost_usd == pytest.approx(11_476 / 25_000_000)


# --------------------------------------------------------------------------- #
# Window filtering
# --------------------------------------------------------------------------- #


def test_since_hours_excludes_older_cycles() -> None:
    old = datetime(2026, 10, 1, 8, 0, tzinfo=UTC)
    new = datetime(2026, 10, 2, 8, 0, tzinfo=UTC)
    lines = [
        _cycle_line(timestamp=old.isoformat().replace("+00:00", "Z")),
        _cycle_line(timestamp=new.isoformat().replace("+00:00", "Z")),
    ]
    cutoff = new - timedelta(hours=1)
    events = list(report.iter_events(lines))
    cycles = report.derive_cycles(events)
    kept = [c for c in cycles if c.timestamp is not None and c.timestamp >= cutoff]
    assert len(kept) == 1
    assert kept[0].timestamp == new


def test_unparsable_timestamp_is_not_dropped_silently() -> None:
    """A cycle with no readable timestamp still counts; it just cannot be filtered."""
    line = _cycle_line().replace("'timestamp': '2026-10-02T08:54:02.633744Z'", "")
    cycles = report.derive_cycles(list(report.iter_events([line])))
    assert len(cycles) == 1
    assert cycles[0].timestamp is None


# --------------------------------------------------------------------------- #
# Report rendering
# --------------------------------------------------------------------------- #


def test_report_reports_zero_pressure_and_says_so() -> None:
    lines = [_cycle_line(), _task_line()]
    out = report.build_report(lines, None, "test")

    assert "cycle lines (one per symbol)   1" in out
    assert "llm_rate_limited" in out
    # Zero rows must be labelled as clean rather than left blank.
    rate_row = next(
        line for line in out.splitlines() if line.strip().startswith("llm_rate_limited")
    )
    assert "NON-ZERO" not in rate_row


def test_report_flags_nonzero_pressure() -> None:
    lines = [_cycle_line(rate_limited=2, failures=1), _task_line()]
    out = report.build_report(lines, None)
    assert out.count("NON-ZERO") >= 2


def test_report_lists_fallback_events() -> None:
    lines = [
        _cycle_line(),
        "worker-1 | {'event': 'narrator.llm_failed', 'reason': 'timeout'}",
        "worker-1 | {'event': 'sentiment.llm_failed', 'reason': 'rate_limited'}",
    ]
    out = report.build_report(lines, None)
    assert "FALLBACK narrator.llm_failed x1" in out
    assert "FALLBACK sentiment.llm_failed x1" in out


def test_report_says_no_fallbacks_when_clean() -> None:
    out = report.build_report([_cycle_line()], None)
    assert "no *_failed fallback events" in out


def test_report_notes_worker_restarts() -> None:
    lines = [
        _cycle_line(calls=7, prompt=1775, completion=1094),
        _cycle_line(calls=6, prompt=1500, completion=1000),
    ]
    out = report.build_report(lines, None)
    assert "worker restart(s) detected" in out


def test_report_handles_an_empty_window_without_raising() -> None:
    out = report.build_report([], None, "empty")
    assert "No cycle lines in this window" in out


def test_report_projects_a_daily_figure_over_a_full_window() -> None:
    """Two cycles an hour apart should project a daily cost."""
    first = datetime(2026, 10, 2, 8, 0, tzinfo=UTC).isoformat().replace(
        "+00:00", "Z"
    )
    second = datetime(2026, 10, 2, 9, 0, tzinfo=UTC).isoformat().replace(
        "+00:00", "Z"
    )
    lines = [
        _cycle_line(timestamp=first),
        _cycle_line(
            symbol="BTCUSD", calls=14, prompt=3550, completion=2188, timestamp=second
        ),
    ]
    out = report.build_report(lines, None)
    assert "observed cost_usd/day" in out
    assert "projected cost_usd/month" in out


def test_report_suppresses_a_projection_from_a_short_window() -> None:
    """Extrapolating from minutes yields a confident but meaningless daily rate."""
    first = datetime(2026, 10, 2, 8, 0, tzinfo=UTC).isoformat().replace(
        "+00:00", "Z"
    )
    second = datetime(2026, 10, 2, 8, 0, 36, tzinfo=UTC).isoformat().replace(
        "+00:00", "Z"
    )
    lines = [
        _cycle_line(timestamp=first),
        _cycle_line(
            symbol="BTCUSD", calls=14, prompt=3550, completion=2188, timestamp=second
        ),
    ]
    out = report.build_report(lines, None)
    assert "projection suppressed" in out
    assert "observed cost_usd/day" not in out


# --------------------------------------------------------------------------- #
# --validate: format check, deliberately not a verdict
# --------------------------------------------------------------------------- #


def test_validation_reports_full_parse_coverage_on_real_lines() -> None:
    out = report.build_validation([_cycle_line(), _task_line()])
    assert "UNPARSABLE, not a task line    0" in out
    assert "cycle_complete lines          1" in out
    assert "duration matched" in out


def test_validation_flags_an_unparsable_event_line() -> None:
    """A truncated or reformatted event line must surface, not vanish."""
    out = report.build_validation(["worker-1 | {'symbol': 'XAUUSD', 'calls': "])
    assert "UNPARSABLE, not a task line    1" in out
    assert "'symbol': 'XAUUSD'" in out


def test_celery_task_result_lines_are_not_counted_as_drift() -> None:
    """Celery truncates long task return values; those are not format drift.

    Observed on the live log: ``... succeeded in 71.8s: [{'symbol': 'XAUUSD',
    ..., 'technical': {'agent': 'technical_analyst', 'symb...', ...}}]`` — the
    ``...}]]`` tail cannot be literal_eval'd. An earlier validator reported
    these as unparsable, which would cry wolf on every single cycle.
    """
    task_line = (
        "worker-1  | [2026-10-02 08:54:38,606: INFO/ForkPoolWorker-2] Task "
        "orchestrator.scheduler.analyze_all_symbols"
        "[01bca656-5774-4e9b-8daf-a384449c2f42] succeeded in 71.83250871999189s: "
        "[{'symbol': 'XAUUSD', 'decision': {'reasoning': 'x'}, "
        "'technical': {'agent': 'technical_analyst', 'symb...', ...}}]"
    )
    assert report.parse_event(task_line) is None
    out = report.build_validation([task_line])
    assert "Celery task-result lines       1" in out
    assert "UNPARSABLE, not a task line    0" in out
    assert "no format drift" in out


def test_validation_separates_task_lines_from_real_drift() -> None:
    """A genuine event failure and a Celery line are counted separately."""
    lines = [
        _cycle_line(),
        # Celery line: truncated return value.
        "worker-1 | [t] INFO/Pool-2] Task pkg.fn[aa-bb] succeeded in 1.0s: "
        "[{'a': 1, 'b': 'trunc...', ...}]",
        # Real drift: an event-shaped line that will not parse.
        "worker-1 | {'symbol': 'XAUUSD', 'calls': ",
    ]
    out = report.build_validation(lines)
    assert "Celery task-result lines       1" in out
    assert "UNPARSABLE, not a task line    1" in out
    assert "no format drift" not in out


def test_validation_lists_every_counter_the_parser_relies_on() -> None:
    out = report.build_validation([_cycle_line()])
    assert "MISSING COUNTERS" not in out
    assert "MISSING IDENTIFIERS" not in out
    for key in ("llm_calls", "llm_cost_units", "llm_prompt_tokens"):
        assert key in out


def test_validation_reports_a_renamed_counter() -> None:
    """A rename is the drift that matters: the old name disappears silently."""
    renamed = _cycle_line().replace("'llm_cost_units':", "'llm_spend_units':")
    out = report.build_validation([renamed])
    assert "MISSING COUNTERS: llm_cost_units" in out
    assert "llm_spend_units" in out  # also surfaced as an unknown field


def test_validation_notes_a_benign_additive_field() -> None:
    """An added field is benign but should still be visible."""
    extended = _cycle_line().replace(
        "'llm_cache_hit_rate': 0.0,", "'llm_cache_hit_rate': 0.0, 'llm_new_metric': 3,"
    )
    out = report.build_validation([extended])
    assert "MISSING COUNTERS" not in out
    assert "llm_new_metric" in out
    assert "benign if additive" in out


def test_validation_survives_a_log_with_no_cycle_lines() -> None:
    out = report.build_validation(["worker-1 | Scheduler: Sending due task foo"])
    assert "cycle_complete lines          0" in out
    assert "field coverage cannot be checked" in out


def test_validation_lists_observed_event_names() -> None:
    lines = [
        _cycle_line(),
        "worker-1 | {'event': 'llm.usage', 'prompt_tokens': 1}",
        "worker-1 | {'event': 'narrator.llm_failed', 'reason': 'timeout'}",
    ]
    out = report.build_validation(lines)
    assert "pipeline.cycle_complete" in out
    assert "llm.usage" in out
    assert "narrator.llm_failed" in out


def test_validation_emits_no_statistics_or_verdict() -> None:
    """A format check must not be quotable as a stability result.

    If --validate ever printed a cost or a distribution, its output could be
    mistaken for the window's verdict and quoted as one.
    """
    out = report.build_validation([_cycle_line(), _task_line()])
    # Field *names* may legitimately appear (that is the point of the field
    # listing), so this forbids the rendered statistic forms rather than the
    # bare substrings.
    for forbidden in (
        "min=",
        "median=",
        "max=",
        "p95=",
        "observed cost_usd/day",
        "projected",
        "FALLBACK",
        "no *_failed",
        "NON-ZERO",
        "## Volume",
        "## Pressure counters",
        "## Totals",
    ):
        assert forbidden not in out, f"validate output leaked a statistic: {forbidden}"


def test_validate_flag_short_circuits_the_report(monkeypatch, capsys) -> None:
    """--validate must return before build_report can print anything."""
    import io

    monkeypatch.setattr(
        report.sys,
        "stdin",
        io.StringIO(_cycle_line() + "\n" + _task_line() + "\n"),
    )
    assert report.main(["--validate"]) == 0
    captured = capsys.readouterr().out
    assert "Parser validation" in captured
    assert "## Volume" not in captured
    assert "## Pressure counters" not in captured


def test_report_sections_are_in_order() -> None:
    """Every section header must appear, and in the order build_report emits them.

    An earlier version printed distribution rows directly instead of appending
    them, so they flushed ahead of the assembled report and the output was
    visibly scrambled with no section headers attached to their own data.
    """
    out = report.build_report([_cycle_line(), _task_line()], None, "order")
    headings = [
        line for line in out.splitlines() if line.startswith("## ")
    ]
    assert headings == [
        "## Volume",
        "## Task wall time (from the Celery succeeded line)",
        "## Per-cycle cost and tokens (differenced, not cumulative)",
        "## Pressure counters (per-cycle sums)",
        "## Totals and projection",
        "## Anomalies",
    ]
    # The header must come before the data it labels.
    assert out.index("# order") < out.index("## Volume")
    assert out.index("## Volume") < out.index("cost_usd")
    assert out.index("cost_usd") < out.index("## Pressure counters")
