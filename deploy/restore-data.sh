#!/usr/bin/env bash
#
# Restore Pkay TDAI's persistent data from a backup made by deploy/backup-data.sh.
#
# Usage:  bash deploy/restore-data.sh backups/pkay-data-20260919-160114.tar.gz
set -euo pipefail

FILE="${1:?usage: restore-data.sh <path-to-pkay-data-*.tar.gz>}"
VOLUME="${VOLUME:-pkay-tdai_pkay_data}"

if [ ! -f "$FILE" ]; then
  echo "Backup file not found: $FILE" >&2
  exit 1
fi

ABS_DIR="$(cd "$(dirname "$FILE")" && pwd)"
BASE="$(basename "$FILE")"

docker volume create "$VOLUME" >/dev/null

docker run --rm \
  -v "${VOLUME}:/data" \
  -v "${ABS_DIR}:/backup:ro" \
  alpine sh -c "rm -rf /data/* && tar xzf /backup/${BASE} -C /data"

echo "✓ Restored ${BASE} into volume ${VOLUME}"
echo "Restart the API so it reloads the stores:"
echo "  docker compose -f docker-compose.prod.yml --env-file .env.production restart api"
