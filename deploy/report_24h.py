#!/usr/bin/env python3
"""Per-cycle report over the analysis window, read from worker logs.

Reads ``docker compose logs worker`` text on stdin and reports per-cycle
distributions. Deliberately does **not** read cumulative counters at face value:
``pipeline.cycle_complete`` counts are cumulative for the worker process, so a
worker restart mid-window would make the totals look like a spend spike. This
differences consecutive lines and restarts the baseline when a counter goes
backwards.

Every field is read out of the parsed event dict by exact key. Earlier versions
of the monitoring greps matched the bare string ``429`` and matched dotted event
names, both of which produced phantom hits — Celery task UUIDs contain digit
runs, and ``llm.usage_missing`` matches the ``llm_usage_missing`` *field* on a
cycle line. Parsing first removes that whole class of error.

Run it through ``deploy/report-24h.sh``, which pipes the logs in.

Where it lives on the server: the Dockerfile does not COPY ``deploy/`` into the
image, and ``/opt/pkay/deploy/`` does not carry this file either. Until it is
copied there, invoke the parser directly — it is self-contained and imports
``UNITS_PER_USD`` from the container's own installed package:

    docker cp report_24h.py "<worker-container>":/tmp/pkay-report/report_24h.py
    docker compose -f docker-compose.prod.yml --env-file .env.production \\
      logs --no-color --timestamps worker \\
      | docker exec -i "<worker-container>" python3 /tmp/pkay-report/report_24h.py \\
          --since-hours 24 --label "24h stability window"

Usage:  python3 report_24h.py [--since-hours 24] [--label "..."] [--validate]
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from collections.abc import Iterable, Iterator, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

try:  # Prefer the deployed rate so the report cannot drift from the code.
    from shared.config import UNITS_PER_USD
except Exception:
    # Running outside the app, or the import chain failed for some unrelated
    # reason. Observed in production: a stray /tmp/inspect.py in the container
    # shadowed the stdlib `inspect` module, so importing pydantic raised
    # AttributeError rather than ImportError and the whole parser died with a
    # traceback about a module it never mentioned. Catching only
    # ModuleNotFoundError would not have survived that.
    #
    # The fallback value is kept identical to shared/config.py. The wrapper
    # script runs this inside the worker container, where the import above is
    # the path actually used; the constant is only a safety net for a report
    # run from the deploy/ directory on a host without the app installed.
    UNITS_PER_USD = 25_000_000

CYCLE_EVENT = "pipeline.cycle_complete"

#: Counters differenced between consecutive cycle lines. Listed explicitly so a
#: new counter in the log cannot silently join this set.
DIFFERENCED = (
    "llm_calls",
    "llm_attempts",
    "llm_retries",
    "llm_rate_limited",
    "llm_timeouts",
    "llm_budget_exhausted",
    "llm_failures",
    "llm_prompt_tokens",
    "llm_completion_tokens",
    "llm_cached_tokens",
    "llm_total_tokens",
    "llm_cost_units",
    "llm_usage_missing",
)

#: Events that mean the pipeline degraded rather than produced a real result.
FALLBACK_SUFFIX = "_failed"

_TASK_DURATION = re.compile(
    r"analyze_all_symbols\[[0-9a-f-]+\] succeeded in ([0-9.]+)s"
)

#: Celery's own task lines, e.g. ``Task pkg.mod.fn[id] succeeded in 71.8s: [...]``.
#: Their trailing return value is truncated for long results, so they are not
#: structured events and must never be counted as parse failures.
_TASK_RESULT = re.compile(r"\bTask\s+\S+\[[0-9a-f-]+\]\s+(succeeded|raised)\b")

#: Milliseconds-only fields that must be summed per symbol before dividing.
_MS = 1000.0


def _parse_iso(value: Any) -> datetime | None:
    """Parse the log's ISO-8601 timestamp, tolerating a missing or odd value."""
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def parse_event(line: str) -> dict[str, Any] | None:
    """Extract the structured event dict from a log line.

    The dict is Python repr, so ``ast.literal_eval`` is the correct parser — it
    evaluates no code and fails cleanly on a truncated line. Returns ``None`` for
    any line that does not carry a parsable dict, which is every non-event line.
    """
    start = line.find("{")
    if start < 0:
        return None
    try:
        parsed = ast.literal_eval(line[start:])
    except (ValueError, SyntaxError):
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def iter_events(lines: Iterable[str]) -> Iterator[dict[str, Any]]:
    """Yield every line that carries a structured event dict."""
    for line in lines:
        event = parse_event(line)
        if event is not None:
            yield event


def _is_task_result_line(line: str) -> bool:
    """True for Celery's own task lines, whose trailing value is not an event."""
    return _TASK_RESULT.search(line) is not None


def _number(value: Any) -> float:
    """Coerce a log field to a float, treating anything else as zero."""
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0


class Cycle:
    """One symbol's analysis cycle, with per-cycle rather than cumulative figures."""

    __slots__ = (
        "correlation_id",
        "cost_usd",
        "counters",
        "symbol",
        "timestamp",
        "wall_seconds",
        "worker_epoch",
    )

    def __init__(
        self,
        timestamp: datetime | None,
        symbol: str,
        correlation_id: str,
        wall_seconds: float,
        counters: dict[str, float],
        worker_epoch: int,
    ) -> None:
        self.timestamp = timestamp
        self.symbol = symbol
        self.correlation_id = correlation_id
        self.wall_seconds = wall_seconds
        self.counters = counters
        self.worker_epoch = worker_epoch
        # cost_usd is rounded to 6dp in the log line; recover full precision from
        # cost_units so a per-cycle dollar figure is not quantised to 6 decimals.
        self.cost_usd = counters["llm_cost_units"] / UNITS_PER_USD

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"Cycle({self.symbol} {self.timestamp} "
            f"calls={self.counters['llm_calls']:.0f} usd={self.cost_usd:.6f})"
        )


def derive_cycles(events: Sequence[dict[str, Any]]) -> list[Cycle]:
    """Turn cumulative cycle lines into per-cycle deltas.

    A counter that decreases means the worker process restarted, which resets
    every counter to zero. The new line then becomes the baseline rather than a
    negative delta. The first line of an epoch needs no special handling: it is
    emitted after that symbol's own work, so its absolute value is already that
    symbol's cost, not a leftover.
    """
    cycles: list[Cycle] = []
    previous: dict[str, float] | None = None
    epoch = 0

    for event in events:
        if event.get("event") != CYCLE_EVENT:
            continue

        absolute = {key: _number(event.get(key)) for key in DIFFERENCED}

        if previous is None:
            deltas = dict(absolute)
            epoch = 1
        elif any(absolute[key] < previous[key] for key in DIFFERENCED):
            epoch += 1
            deltas = dict(absolute)
        else:
            deltas = {
                key: absolute[key] - previous[key] for key in DIFFERENCED
            }

        cycles.append(
            Cycle(
                timestamp=_parse_iso(event.get("timestamp")),
                symbol=str(event.get("symbol", "?")),
                correlation_id=str(event.get("correlation_id", "?")),
                wall_seconds=0.0,
                counters=deltas,
                worker_epoch=epoch,
            )
        )
        previous = absolute

    return cycles


def percentile(values: Sequence[float], fraction: float) -> float:
    """Linear-interpolated percentile. Returns 0.0 for an empty input."""
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = fraction * (len(ordered) - 1)
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    weight = position - low
    return ordered[low] * (1.0 - weight) + ordered[high] * weight


def median(values: Sequence[float]) -> float:
    """Median, defined as the 50th percentile."""
    return percentile(values, 0.5)


def _distribution(label: str, values: Sequence[float], fmt: str = "{:.2f}") -> list[str]:
    """Render min / median / max / p95 for one series.

    Returns lines rather than printing them. Printing directly here would flush
    ahead of the assembled report and scramble the output, since ``build_report``
    emits one joined block at the end.
    """
    if not values:
        return [f"  {label:<28s} (no data)"]
    return [
        f"  {label:<28s} n={len(values):<4d} "
        f"min={fmt.format(min(values))}  "
        f"median={fmt.format(median(values))}  "
        f"max={fmt.format(max(values))}  "
        f"p95={fmt.format(percentile(values, 0.95))}"
    ]


def _count_events(events: Sequence[dict[str, Any]]) -> dict[str, int]:
    """Count events by name, restricted to the ``event`` field's value.

    Matching on the parsed value is what keeps ``llm.usage_missing`` from
    matching the ``llm_usage_missing`` field on an unrelated cycle line.
    """
    counts: dict[str, int] = {}
    for event in events:
        name = event.get("event")
        if not isinstance(name, str):
            continue
        counts[name] = counts.get(name, 0) + 1
    return counts


def build_report(
    lines: Sequence[str],
    since: datetime | None,
    label: str = "",
) -> str:
    """Render the full report for the given log lines."""
    events = list(iter_events(lines))
    cycles = derive_cycles(events)
    epochs = sorted({c.worker_epoch for c in cycles})

    if since is not None:
        cycles = [
            c for c in cycles if c.timestamp is not None and c.timestamp >= since
        ]

    out: list[str] = []
    if label:
        out.append(f"# {label}")
    out.append(f"Window since : {since.isoformat() if since else 'all available'}")
    if cycles:
        stamps = [c.timestamp for c in cycles if c.timestamp is not None]
        if stamps:
            out.append(
                f"Observed     : {min(stamps).isoformat()} .. {max(stamps).isoformat()}"
            )
    out.append("")

    # --- Volume ------------------------------------------------------------ #
    out.append("## Volume")
    out.append(f"  cycle lines (one per symbol)   {len(cycles)}")
    out.append(f"  worker epochs (restarts)       {len(epochs)}")
    symbols = sorted({c.symbol for c in cycles})
    out.append(f"  symbols                        {', '.join(symbols) or 'none'}")
    out.append("")

    if not cycles:
        out.append("No cycle lines in this window — check the log window or the label.")
        return "\n".join(out)

    # --- Wall time --------------------------------------------------------- #
    out.append("## Task wall time (from the Celery succeeded line)")
    durations = [
        float(m.group(1))
        for m in (_TASK_DURATION.search(line) for line in lines)
        if m is not None
    ]
    out.extend(_distribution("task wall seconds", durations))
    if durations:
        total_hours = sum(durations) / _MS
        out.append(f"  {'summed cycle hours':<28s} {total_hours:.2f}")
    out.append("")

    # --- Per-cycle cost and tokens ----------------------------------------- #
    out.append("## Per-cycle cost and tokens (differenced, not cumulative)")
    out.extend(_distribution("cost_usd", [c.cost_usd for c in cycles], "{:.6f}"))
    out.extend(
        _distribution(
            "cost_units", [c.counters["llm_cost_units"] for c in cycles], "{:.0f}"
        )
    )
    out.extend(
        _distribution(
            "prompt_tokens", [c.counters["llm_prompt_tokens"] for c in cycles], "{:.0f}"
        )
    )
    out.extend(
        _distribution(
            "completion_tokens",
            [c.counters["llm_completion_tokens"] for c in cycles],
            "{:.0f}",
        )
    )
    out.extend(
        _distribution(
            "total_tokens", [c.counters["llm_total_tokens"] for c in cycles], "{:.0f}"
        )
    )
    out.extend(
        _distribution(
            "cached_tokens", [c.counters["llm_cached_tokens"] for c in cycles], "{:.0f}"
        )
    )
    out.extend(
        _distribution("llm_calls", [c.counters["llm_calls"] for c in cycles], "{:.1f}")
    )
    out.append("")

    # --- Pressure: must be zero -------------------------------------------- #
    out.append("## Pressure counters (per-cycle sums)")
    for key in (
        "llm_rate_limited",
        "llm_retries",
        "llm_timeouts",
        "llm_budget_exhausted",
        "llm_failures",
        "llm_usage_missing",
    ):
        total = sum(c.counters[key] for c in cycles)
        flag = "" if total == 0 else "   <-- NON-ZERO"
        out.append(f"  {key:<28s} {total:.0f}{flag}")
    out.append("")

    # --- Totals and projection --------------------------------------------- #
    out.append("## Totals and projection")
    total_usd = sum(c.cost_usd for c in cycles)
    total_tokens = sum(c.counters["llm_total_tokens"] for c in cycles)
    out.append(f"  {'total cost_usd':<28s} {total_usd:.6f}")
    out.append(f"  {'total tokens':<28s} {total_tokens:.0f}")
    if cycles and stamps:
        span = (max(stamps) - min(stamps)).total_seconds()
        span_hours = span / 3600.0
        out.append(f"  {'observed window hours':<28s} {span_hours:.2f}")
        # Extrapolating from a window of minutes produces a confident-looking but
        # meaningless daily rate, which is worse than no rate at all. Require an
        # hour of observed data before projecting.
        if span_hours >= 1.0:
            per_day = total_usd / span * 86400.0
            out.append(f"  {'observed cost_usd/day':<28s} {per_day:.4f}")
            out.append(
                f"  {'observed tokens/day':<28s} {total_tokens / span * 86400.0:.0f}"
            )
            out.append(f"  {'projected cost_usd/month':<28s} {per_day * 30.4:.4f}")
        else:
            out.append(
                f"  projection suppressed: {span_hours:.2f}h of data is below the"
                " 1h minimum. Wait for a full window."
            )
    out.append("")

    # --- Anomalies --------------------------------------------------------- #
    out.append("## Anomalies")
    counts = _count_events(events)
    degraded = sorted(
        (name, n) for name, n in counts.items() if name.endswith(FALLBACK_SUFFIX)
    )
    if degraded:
        for name, n in degraded:
            out.append(f"  FALLBACK {name} x{n}")
    else:
        out.append("  no *_failed fallback events")

    for interesting in ("llm.usage_missing", "bus.redis_degraded", "bus.redis_reconnected"):
        n = counts.get(interesting, 0)
        if n:
            out.append(f"  {interesting} x{n}")

    slow = [c for c in cycles if c.wall_seconds > 300.0]
    if slow:
        out.append(f"  {len(slow)} cycle(s) over 300s wall time")
    if len(epochs) > 1:
        out.append(
            f"  {len(epochs) - 1} worker restart(s) detected — cumulative counters"
            " were re-based, which is why this report differences them"
        )
    out.append("")
    return "\n".join(out)


def build_validation(lines: Sequence[str]) -> str:
    """Report whether the parser still understands the log, without judging it.

    This deliberately emits **no** statistics: no cost, no wall-time
    distribution, no pass/fail against the enable checklist. Its only question is
    "does this parser still read this format", which is a different question from
    "is the window clean". Keeping them separate means a format check cannot be
    mistaken for a stability verdict, or quoted as one.

    Checks:
      - every line carrying a dict is parsable (unparsable dict lines are drift)
      - the fields this parser depends on are all present on cycle lines
      - newly appearing fields, so a rename is visible rather than silently zero
      - the Celery succeeded line still matches
      - cycle lines and task lines are present at all
    """
    out: list[str] = ["# Parser validation (no window statistics)"]
    out.append("")

    dict_lines = [line for line in lines if "{" in line]
    parsed = [parse_event(line) for line in dict_lines]
    failed = [
        line for line, event in zip(dict_lines, parsed, strict=True) if event is None
    ]
    # Not every brace-line is a structured event. Celery's own task lines end
    # with the task's return value, and it truncates long ones ("'symb...', ...
    # }}]"), so literal_eval cannot parse them — correctly. Counting those as
    # format drift would cry wolf on every cycle, so they are classified apart
    # from a genuine event that stopped parsing.
    task_result = [line for line in failed if _is_task_result_line(line)]
    drift = [line for line in failed if not _is_task_result_line(line)]

    out.append("## Format")
    out.append(f"  total lines                    {len(lines)}")
    out.append(f"  lines carrying a dict          {len(dict_lines)}")
    out.append(f"  parsed as structured events    {len(dict_lines) - len(failed)}")
    out.append(
        f"  Celery task-result lines       {len(task_result)}"
        "  (truncated return values, not events)"
    )
    out.append(f"  UNPARSABLE, not a task line    {len(drift)}")
    for line in drift[:3]:
        out.append(f"      {line.strip()[:110]}")
    if not drift and task_result:
        out.append("  -> no format drift: the only failures are Celery's own")
        out.append("     truncated task return values, which are not events.")
    out.append("")

    events = [event for event in parsed if event is not None]
    cycles = [event for event in events if event.get("event") == CYCLE_EVENT]
    out.append("## Coverage")
    out.append(f"  cycle_complete lines          {len(cycles)}")
    task_lines = [
        line for line in lines if "analyze_all_symbols" in line and "succeeded in" in line
    ]
    matched = [line for line in task_lines if _TASK_DURATION.search(line)]
    out.append(f"  task succeeded lines          {len(task_lines)}")
    out.append(f"  of those, duration matched   {len(matched)}")
    out.append("")

    if not cycles:
        out.append("## Fields")
        out.append("  no cycle lines present, so field coverage cannot be checked")
        out.append("")
        return "\n".join(out)

    present: dict[str, int] = {}
    for event in cycles:
        for key in event:
            present[key] = present.get(key, 0) + 1

    out.append("## Fields the parser depends on")
    missing = [key for key in DIFFERENCED if key not in present]
    absent = [key for key in ("symbol", "correlation_id", "timestamp") if key not in present]
    for key in DIFFERENCED:
        if key in present:
            out.append(f"  {key:<28s} present on {present[key]}/{len(cycles)} lines")
    for key in ("symbol", "correlation_id", "timestamp"):
        if key in present:
            out.append(f"  {key:<28s} present on {present[key]}/{len(cycles)} lines")
    if missing:
        out.append(f"  MISSING COUNTERS: {', '.join(missing)}")
        out.append("    -> these would silently difference as 0")
    if absent:
        out.append(f"  MISSING IDENTIFIERS: {', '.join(absent)}")
    out.append("")

    known = set(DIFFERENCED) | {"symbol", "correlation_id", "timestamp", "event"}
    new_fields = sorted(key for key in present if key not in known)
    out.append("## Fields present but not read by this parser")
    if new_fields:
        for key in new_fields:
            out.append(f"  {key:<28s} on {present[key]}/{len(cycles)} lines")
        out.append("  -> benign if additive. A RENAME appears here AND as a")
        out.append("     missing counter above; that pairing is the signal to act on.")
    else:
        out.append("  none")
    out.append("")

    # Every event name seen, so an unexpected one is visible without grepping.
    names = sorted({str(e.get("event")) for e in events if e.get("event")})
    out.append("## Event names observed")
    for name in names:
        out.append(f"  {name}")
    out.append("")
    return "\n".join(out)


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--since-hours",
        type=float,
        default=None,
        help="only include cycles newer than this many hours",
    )
    parser.add_argument("--label", default="", help="heading for the report")
    parser.add_argument(
        "--now",
        default=None,
        help="ISO timestamp to measure back from; defaults to the current time",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help=(
            "report only whether this parser still understands the log format; "
            "emits no statistics and no pass/fail verdict"
        ),
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(list(argv) if argv is not None else sys.argv[1:])
    lines = sys.stdin.read().splitlines()

    # Validate before anything else and return: --validate must never print
    # window statistics, or its output could be quoted as a stability verdict.
    if args.validate:
        print(build_validation(lines))
        return 0

    now = _parse_iso(args.now) if args.now else datetime.now(UTC)
    since = None
    if args.since_hours is not None and now is not None:
        since = now - timedelta(hours=args.since_hours)

    print(build_report(lines, since, args.label))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
