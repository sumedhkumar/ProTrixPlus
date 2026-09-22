#!/usr/bin/env bash
# Combined api+worker entrypoint for the free Render deploy (see
# infra/render/combined.Dockerfile). Migrate + seed (api's job, same as
# api/scripts/entrypoint.sh), then run worker and api as sibling background
# processes so a TERM/INT to this script (PID 1) stops both cleanly.
set -euo pipefail

# Redis is not optional here, and it has no sane default in a container:
# PROTRIX_REDIS_URL is `sync: false` in render.yaml (the URL is a secret, so the
# blueprint can't carry it), and when it's unset both api and worker quietly
# fall back to redis://localhost:6379/0 - where nothing is listening. The worker
# then burns 60 one-second retries logging a bare "ConnectionError", exits, and
# takes the api down with it. Check it up front instead, and say so plainly.
echo "[combined] checking redis..."
python - <<'PY'
import os
import sys
from urllib.parse import urlparse

from redis import Redis

url = os.environ.get("PROTRIX_REDIS_URL", "").strip()
if not url:
    sys.exit(
        "[combined] PROTRIX_REDIS_URL is not set.\n"
        "[combined] Render's blueprint marks it `sync: false` because the URL is a\n"
        "[combined] secret - set it in the service's Environment tab. See step 2 of\n"
        "[combined] docs/DEPLOY-RENDER.md (create a free Upstash Redis, paste the\n"
        "[combined] rediss:// 'Redis Connect' URL - the TLS one, not the REST URL)."
    )

# Never log the URL itself; it carries the password.
parsed = urlparse(url)
where = f"{parsed.hostname or '<no host>'}:{parsed.port}" if parsed.port else (parsed.hostname or "<no host>")
try:
    Redis.from_url(url, socket_connect_timeout=5).ping()
except Exception as exc:  # noqa: BLE001
    sys.exit(f"[combined] redis at {where} did not answer: {exc.__class__.__name__}: {exc}")
print(f"[combined] redis is up ({where})")
PY

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

# A Postgres advisory lock serializes migrate+seed across container
# instances. Render's health-check-driven restarts can briefly overlap an
# old crash-looping instance with a new one, and two concurrent
# `alembic upgrade head` runs both doing their own "does this table exist?"
# check race and can both try to CREATE TABLE the same object. The lock is
# held for one psycopg session spanning both subprocess calls (session-level
# advisory locks aren't tied to a transaction), so a second instance blocks
# here until the first fully finishes instead of racing it.
echo "[combined] waiting for migration lock..."
python - <<'PY'
import os
import subprocess
import sys

from sqlalchemy import create_engine, text
from protrix_contracts.db.session import normalize_database_url

url = normalize_database_url(os.environ["PROTRIX_DATABASE_URL"])
conn = create_engine(url).connect()
conn.execute(text("SELECT pg_advisory_lock(727310001)"))
conn.commit()
print("[combined] migration lock acquired")
try:
    print("[combined] running migrations...")
    subprocess.run(["alembic", "upgrade", "head"], cwd="/app/api", check=True)
    print("[combined] seeding fake data...")
    subprocess.run(["python", "-m", "app.seed"], cwd="/app/api", check=True)
finally:
    conn.execute(text("SELECT pg_advisory_unlock(727310001)"))
    conn.commit()
    conn.close()
PY

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
