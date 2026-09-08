#!/usr/bin/env bash
# Wait for postgres + the schema (api owns migrations) and redis, then exec.
set -euo pipefail

echo "[entrypoint] waiting for postgres schema + redis..."
python - <<'PY'
import os, time, sys
from sqlalchemy import create_engine, text
from protrix_contracts.db.session import normalize_database_url
import redis as redis_lib

db = normalize_database_url(os.environ["PROTRIX_DATABASE_URL"])
rd = os.environ.get("PROTRIX_REDIS_URL", "redis://redis:6379/0")
for attempt in range(120):
    try:
        with create_engine(db).connect() as c:
            c.execute(text("SELECT 1 FROM signals LIMIT 1"))
        redis_lib.from_url(rd).ping()
        print("[entrypoint] deps ready")
        break
    except Exception as exc:  # noqa: BLE001
        print(f"[entrypoint] not ready ({attempt}): {exc.__class__.__name__}")
        time.sleep(1)
else:
    sys.exit("[entrypoint] deps never became ready")
PY

echo "[entrypoint] exec: $*"
exec "$@"
