#!/usr/bin/env bash
#
# Safe redeploy: back up persistent data, prove the accounts survive, rebuild, then
# prove they still survived.
#
# The named `pkay_data` volume already survives `up -d --build`, and we snapshot it
# first so a failed migration or a disk-level rebuild is recoverable. What this adds
# is the check that was missing: a record/verify pair around the rebuild, so a code
# change that cannot read an existing record fails the deploy loudly instead of
# quietly serving an empty user table.
#
# Usage:  bash deploy/redeploy.sh
set -euo pipefail

cd "$(dirname "$0")/.."

COMPOSE=(docker compose -f docker-compose.prod.yml --env-file .env.production)

echo "==> Backing up data volume before redeploy"
bash deploy/backup-data.sh

echo
echo "==> Recording the user count before rebuild"
bash deploy/preflight-data.sh record

echo
echo "==> Rebuilding and restarting the stack"
"${COMPOSE[@]}" up -d --build

echo
echo "==> Verifying user data survived the rebuild"
# Deliberately not `|| true`: a dropped account must stop the deploy, not be noted.
bash deploy/preflight-data.sh verify

echo
echo "==> Status"
"${COMPOSE[@]}" ps
echo
echo "Reminder: copy the newest ./backups/pkay-data-*.tar.gz off the server."