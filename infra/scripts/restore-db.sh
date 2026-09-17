#!/usr/bin/env bash
# Restore infra/backups/<file>.dump (or the most recent backup) into the
# running postgres container. DESTRUCTIVE to whatever is currently in the
# protrix database - it drops and recreates the schema before restoring.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_DIR="$(dirname "$SCRIPT_DIR")"
BACKUP_DIR="$INFRA_DIR/backups"
CONTAINER="protrixplus-postgres-1"

FILE="${1:-}"
if [ -z "$FILE" ]; then
  FILE="$(ls -1t "$BACKUP_DIR"/protrix-*.dump 2>/dev/null | head -n1 || true)"
fi
if [ -z "$FILE" ] || [ ! -f "$FILE" ]; then
  echo "[restore-db] no backup file found. Usage: $0 [path/to/protrix-*.dump]" >&2
  exit 1
fi

if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
  echo "[restore-db] $CONTAINER is not running." >&2
  exit 1
fi

echo "[restore-db] restoring $FILE into $CONTAINER (protrix db) ..."
docker cp "$FILE" "$CONTAINER:/tmp/protrix-restore.dump"
docker exec "$CONTAINER" pg_restore -U protrix -d protrix --clean --if-exists -1 /tmp/protrix-restore.dump
docker exec "$CONTAINER" rm -f /tmp/protrix-restore.dump

echo "[restore-db] done."
