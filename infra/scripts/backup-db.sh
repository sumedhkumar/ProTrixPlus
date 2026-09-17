#!/usr/bin/env bash
# Dump the running postgres container's protrix database to infra/backups/.
# Safe to run any time the stack is up; does not touch the live data.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_DIR="$(dirname "$SCRIPT_DIR")"
BACKUP_DIR="$INFRA_DIR/backups"
CONTAINER="protrixplus-postgres-1"
STAMP="$(date +%Y%m%d-%H%M%S)"
OUT_FILE="$BACKUP_DIR/protrix-$STAMP.dump"

mkdir -p "$BACKUP_DIR"

if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
  echo "[backup-db] $CONTAINER is not running - nothing to back up." >&2
  exit 1
fi

docker exec "$CONTAINER" pg_dump -U protrix -d protrix -Fc -f /tmp/protrix-backup.dump
docker cp "$CONTAINER:/tmp/protrix-backup.dump" "$OUT_FILE"
docker exec "$CONTAINER" rm -f /tmp/protrix-backup.dump

echo "[backup-db] wrote $OUT_FILE"
# Keep only the 10 most recent backups (macOS ships BSD xargs, no -r flag).
ls -1t "$BACKUP_DIR"/protrix-*.dump 2>/dev/null | tail -n +11 | while IFS= read -r old; do
  rm -f -- "$old"
done
