#!/usr/bin/env bash
#
# Per-cycle analysis report over the measurement window.
#
# Read-only: inspects container logs and prints statistics. Changes nothing.
#
# The parser runs inside the worker container so it imports UNITS_PER_USD from
# the deployed shared/config.py rather than a copy that could drift.
#
# Usage:
#   bash deploy/report-24h.sh                        # default 24h window
#   bash deploy/report-24h.sh --since-hours 6
#   bash deploy/report-24h.sh --label "24h stability window"
#
#   bash deploy/report-24h.sh --validate             # format check only
#
# --validate answers only "does this parser still read this format": parse
# coverage, field presence, unknown fields, event names. It prints no statistics
# and no verdict, so it can never be mistaken for a stability judgement.
set -euo pipefail

cd "$(dirname "$0")/.."

COMPOSE=(docker compose -f docker-compose.prod.yml --env-file .env.production)
WORKER=pkay-tdai-worker-1
SCRIPT="$(pwd)/deploy/report_24h.py"

if [ ! -f "$SCRIPT" ]; then
  echo "Cannot find deploy/report_24h.py (looked in $SCRIPT)" >&2
  exit 1
fi

# A container id is more robust than the hard-coded name, which changes if the
# project name does. Fall back to the conventional name when the lookup fails.
CID=$("${COMPOSE[@]}" ps -q worker 2>/dev/null || true)
if [ -z "$CID" ]; then
  echo "worker container not found. Is the stack up?" >&2
  exit 1
fi

# --timestamps keeps the event's own ISO field, which the parser needs to apply
# --since-hours; without it the leading Docker timestamp is all that is left.
LOG_FILE=$(mktemp)
# Assigned before the trap so an early exit still cleans up. `set -u` would
# otherwise fail inside the trap on an unset variable.
TMP_DIR=/tmp/pkay-report

# The trap also removes the parser's directory inside the container. A leftover
# file in /tmp can shadow a stdlib module of the same name — a stray inspect.py
# there broke the parser's pydantic import chain once already.
trap 'rm -f "$LOG_FILE"; docker exec "$CID" rm -rf "$TMP_DIR" >/dev/null 2>&1 || true' EXIT
"${COMPOSE[@]}" logs --no-color --timestamps worker >"$LOG_FILE" 2>&1

LINES=$(wc -l <"$LOG_FILE")
echo "Read $LINES worker log lines." >&2

# docker cp rather than a mount: the deploy bundle has no bind mount for deploy/,
# so the file is not visible inside the container otherwise.
#
# Run from a dedicated subdirectory rather than /tmp directly: the script's own
# directory becomes sys.path[0], so a sibling file there can shadow a stdlib
# module. A stray /tmp/inspect.py broke the pydantic import chain once already,
# killing the parser with an unrelated AttributeError.
# Run from a dedicated subdirectory rather than /tmp directly: the script's own
# directory becomes sys.path[0], so a sibling file there can shadow a stdlib
# module. A stray /tmp/inspect.py broke the pydantic import chain once already.
docker exec "$CID" rm -rf "$TMP_DIR" >/dev/null 2>&1 || true
docker exec "$CID" mkdir -p "$TMP_DIR" >/dev/null
docker cp "$SCRIPT" "${CID}:${TMP_DIR}/report_24h.py" >/dev/null

# Not `exec`: exec would replace this shell, so the EXIT trap never fires and the
# parser's directory would survive in the container.
docker exec -i "$CID" python3 "${TMP_DIR}/report_24h.py" "$@" <"$LOG_FILE"