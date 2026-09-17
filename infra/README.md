# /infra

Local runtime. Docker Compose only - no cloud, no paid services.

| File | Purpose |
| --- | --- |
| `docker-compose.yml` | postgres, redis, api, worker, web |
| `.env.example` | safe placeholder env (copy to `.env`) |
| `postgres/init/01_bootstrap.sql` | one-time DB defaults (UTC). Schema is Alembic's. |
| `scripts/simulate_signal.py` | posts a versioned sample webhook to the api |

## Clean start

**Unix / macOS**

```bash
cp infra/.env.example infra/.env
docker compose -f infra/docker-compose.yml --env-file infra/.env up --build -d
```

**Windows (PowerShell)**

```powershell
Copy-Item infra\.env.example infra\.env
docker compose -f infra/docker-compose.yml --env-file infra/.env up --build -d
```

Wait for health, then:

```bash
curl -fsS localhost:8000/health         # api
curl -fsS localhost:8100/health         # worker
curl -fsS localhost:3000/login          # web
python infra/scripts/simulate_signal.py # fire one mock signal
```

Open http://localhost:3000 .

## Backups

```bash
make backup   # pg_dump the live protrix db to infra/backups/ (kept: last 10)
make restore  # restore the most recent infra/backups/ dump
```

Plain restarts (`docker compose restart postgres`, `up -d`, rebuilding other
services) never touch the postgres volume - only `down -v`, `docker volume
rm`, or `docker system prune --volumes` destroy it.

## Full reset (destructive - wipes every account and signal)

```bash
make reset
```

This auto-runs `make backup` first, then asks you to type `yes` before
running `docker compose -f infra/docker-compose.yml down -v`. Don't run the
raw `down -v` directly - it skips both the backup and the confirmation.
