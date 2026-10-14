#!/usr/bin/env bash
#
# Verify the user-data volume before and after a redeploy.
#
# `docker compose up -d --build` does not touch a named volume, and
# deploy/backup-data.sh snapshots it first. This adds the check that was missing:
# proof that the same accounts are present afterwards, so a bad code change cannot
# quietly drop users and still leave the stack looking healthy.
#
# Usage:
#   bash deploy/preflight-data.sh record   # remember the current user count
#   bash deploy/preflight-data.sh verify   # compare against that count
#   bash deploy/preflight-data.sh check    # validate the store, compare nothing
#
# Exit codes: 0 healthy, 1 problem. `verify` failing after a deploy is the signal to
# restore from the newest ./backups/pkay-data-*.tar.gz.

set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
ENV_FILE="${ENV_FILE:-.env.production}"
STATE_DIR="${STATE_DIR:-.deploy-state}"
STATE_FILE="${STATE_DIR}/user-count"
MODE="${1:-check}"

cd "$(dirname "$0")/.."

COMPOSE=(docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE")

# Print the number of user records, and fail if the store is absent or malformed.
#
# This runs inside the API container rather than a throwaway `alpine`, because
# alpine ships no python3 — parsing the JSON there is not possible. An earlier
# version of this script used alpine and could only ever report "unreadable".
probe() {
  local cid
  cid="$("${COMPOSE[@]}" ps -q api 2>/dev/null || true)"
  if [ -z "$cid" ]; then
    echo "API container is not running; cannot inspect /data/users.json." >&2
    return 1
  fi
  docker exec -i "$cid" python - <<'PY' || return 1
import json
import sys

path = "/data/users.json"
try:
    with open(path) as fh:
        rows = json.load(fh)
except FileNotFoundError:
    print("no users.json yet (fresh install)", file=sys.stderr)
    print(0)
    sys.exit(0)
except Exception as exc:
    print(f"users.json is unreadable: {exc}", file=sys.stderr)
    sys.exit(1)

if not isinstance(rows, list):
    print("users.json is not a list", file=sys.stderr)
    sys.exit(1)

bad = [r for r in rows if not isinstance(r, dict) or not r.get("id") or not r.get("email")]
if bad:
    print(f"{len(bad)} record(s) missing id/email", file=sys.stderr)
    sys.exit(1)

print(len(rows))
PY
}

case "$MODE" in
  record)
    mkdir -p "$STATE_DIR"
    count="$(probe)"
    printf '%s\n' "$count" > "$STATE_FILE"
    echo "Recorded ${count} user record(s) to ${STATE_FILE}"
    ;;

  verify)
    if [ ! -f "$STATE_FILE" ]; then
      echo "No recorded baseline; run 'preflight-data.sh record' before deploying." >&2
      exit 1
    fi
    before="$(cat "$STATE_FILE")"
    after="$(probe)"
    if [ "$before" != "$after" ]; then
      echo "USER COUNT CHANGED: ${before} before, ${after} after." >&2
      echo "Restore with:" >&2
      echo "  bash deploy/restore-data.sh \$(ls -t backups/pkay-data-*.tar.gz | head -1)" >&2
      exit 1
    fi
    echo "User count unchanged at ${after}"
    ;;

  check)
    count="$(probe)"
    echo "users.json OK: ${count} record(s)"
    ;;

  *)
    echo "usage: $0 {record|verify|check}" >&2
    exit 2
    ;;
esac