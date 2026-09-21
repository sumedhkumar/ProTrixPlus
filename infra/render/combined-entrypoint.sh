#!/usr/bin/env bash
# Combined api+worker entrypoint for the free Render deploy (see
# infra/render/combined.Dockerfile). Migrate + seed (api's job, same as
# api/scripts/entrypoint.sh), then run worker and api as sibling background
# processes so a TERM/INT to this script (PID 1) stops both cleanly.
set -euo pipefail

echo "[combined] waiting for postgres..."
python - <<'PY'
import os, time, sys
from sqlalchemy import create_engine, text
from protrix_contracts.db.session import normalize_database_url

url = normalize_database_url(os.environ["PROTRIX_DATABASE_URL"])
for attempt in range(60):
    try:
        create_engine(url).connect().execute(text("SELECT 1"))
        print("[combined] postgres is up")
        break
    except Exception as exc:  # noqa: BLE001
        print(f"[combined] postgres not ready ({attempt}): {exc.__class__.__name__}")
        time.sleep(1)
else:
    sys.exit("[combined] postgres never became ready")
PY

echo "[combined] running migrations..."
(cd /app/api && alembic upgrade head)

echo "[combined] seeding fake data..."
(cd /app/api && python -m app.seed)

# Worker's health server would otherwise also try to bind :8000 (its
# in-container default) and collide with uvicorn; give it its own port.
export PROTRIX_WORKER_HEALTH_PORT="${PROTRIX_WORKER_HEALTH_PORT:-8001}"

echo "[combined] starting worker..."
(cd /app/worker && exec python -m app.main) &
WORKER_PID=$!

echo "[combined] starting api..."
(cd /app/api && exec uvicorn app.main:app --host 0.0.0.0 --port 8000) &
API_PID=$!

trap 'echo "[combined] stopping..."; kill -TERM "$WORKER_PID" "$API_PID" 2>/dev/null || true' TERM INT

wait -n "$WORKER_PID" "$API_PID"
EXIT_CODE=$?
echo "[combined] one process exited ($EXIT_CODE); stopping the other"
kill -TERM "$WORKER_PID" "$API_PID" 2>/dev/null || true
wait || true
exit "$EXIT_CODE"
