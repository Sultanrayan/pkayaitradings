#!/usr/bin/env bash
#
# Back up Pkay TDAI's persistent data (user accounts + access requests).
#
# The API persists these to the `pkay_data` Docker volume (DATA_DIR=/data).
# Run this BEFORE any rebuild, then copy the archive OFF the server — a disk
# wipe removes ./backups too.
#
# Usage:  bash deploy/backup-data.sh
set -euo pipefail

VOLUME="${VOLUME:-pkay-tdai_pkay_data}"
OUT_DIR="${OUT_DIR:-backups}"
TS="$(date +%Y%m%d-%H%M%S)"
ARCHIVE="pkay-data-${TS}.tar.gz"

mkdir -p "$OUT_DIR"

if ! docker volume inspect "$VOLUME" >/dev/null 2>&1; then
  # First deploy: the volume is created by the stack. Nothing to back up yet.
  echo "Volume '$VOLUME' does not exist yet — nothing to back up (first deploy)."
  exit 0
fi

docker run --rm \
  -v "${VOLUME}:/data:ro" \
  -v "$(pwd)/${OUT_DIR}:/backup" \
  alpine sh -c "tar czf /backup/${ARCHIVE} -C /data ."

echo "✓ Wrote ${OUT_DIR}/${ARCHIVE}"
echo
echo "Now copy it off the server so a disk rebuild cannot erase it, e.g.:"
echo "  scp -i \"\$HOME/.ssh/pkay_upcloud\" ${OUT_DIR}/${ARCHIVE} root@94.237.74.255:/root/"
