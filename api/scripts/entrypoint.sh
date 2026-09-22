#!/usr/bin/env bash
# Migrate, seed (idempotent), then exec the given command (uvicorn by default).
set -euo pipefail

echo "[entrypoint] waiting for postgres..."
python - <<'PY'
import os, time, sys
from sqlalchemy import create_engine, text
from protrix_contracts.db.session import normalize_database_url

url = normalize_database_url(os.environ["PROTRIX_DATABASE_URL"])
for attempt in range(60):
    try:
        create_engine(url).connect().execute(text("SELECT 1"))
        print("[entrypoint] postgres is up")
        break
    except Exception as exc:  # noqa: BLE001
        print(f"[entrypoint] postgres not ready ({attempt}): {exc.__class__.__name__}")
        time.sleep(1)
else:
    sys.exit("[entrypoint] postgres never became ready")
PY

echo "[entrypoint] running migrations..."
alembic upgrade head

echo "[entrypoint] exec: $*"
exec "$@"
