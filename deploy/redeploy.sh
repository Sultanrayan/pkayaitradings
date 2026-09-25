#!/usr/bin/env bash
#
# Safe redeploy: back up persistent data first, then rebuild and restart.
#
# The named `pkay_data` volume already survives `up -d --build`, but we always
# snapshot it first so a failed migration or a disk-level rebuild is recoverable.
#
# Usage:  bash deploy/redeploy.sh
set -euo pipefail

cd "$(dirname "$0")/.."

COMPOSE=(docker compose -f docker-compose.prod.yml --env-file .env.production)

echo "==> Backing up data volume before redeploy"
bash deploy/backup-data.sh

echo
echo "==> Rebuilding and restarting the stack"
"${COMPOSE[@]}" up -d --build

echo
echo "==> Status"
"${COMPOSE[@]}" ps
echo
echo "Reminder: copy the newest ./backups/pkay-data-*.tar.gz off the server."
