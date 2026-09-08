# Run the S0 skeleton without Docker (Windows)

Docker Compose is the supported path (`README.md` / `infra/README.md`). This is
the fallback. `run-local.ps1` has two modes:

- **Portable (default, zero‑install)** — `bootstrap` downloads a *portable*
  PostgreSQL 16 and Redis into `<repo>\.localstack\` and runs them on
  **PG 55432 / Redis 6399**, bound to `127.0.0.1`, with **no Windows service, no
  admin, no PATH or registry changes**. `teardown` deletes that folder and the
  machine is exactly as before.
- **System** — if you already run PostgreSQL on `:5432` and Redis on `:6379`,
  skip `bootstrap` and the script uses those.

Either way it launches `api`, `worker`, and `web` from a local Python venv + Node.

## Prerequisites

| Portable mode | System mode |
| --- | --- |
| Node 20–22, Python 3.12+, ~1.5 GB free disk, internet (one‑time ~300 MB download) | the above **plus** a running PostgreSQL 16 on 5432 and a Redis 7 on 6379 |

Node and Python installers: <https://nodejs.org> (LTS), <https://www.python.org/downloads/windows/> ("Add to PATH").

## First run (portable — recommended)

```powershell
cd "C:\Users\HP\Desktop\Protrix plus"
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass    # if scripts are blocked

./run-local.ps1 bootstrap    # download portable PG + Redis, init the db cluster
./run-local.ps1 setup        # venv + python deps + npm ci + alembic upgrade + seed
./run-local.ps1 up           # start infra + api + worker + web  (hidden; logs in .run-local\logs)
./run-local.ps1 status       # ports + /health
```

Then:

```powershell
python infra\scripts\simulate_signal.py    # post one mock signal
start http://localhost:3000                 # open the dashboards
```

Sign in as **USER** or **SUPER_ADMIN** (mock identity, no password) — the signal
and its execution appear.

Add `-Windows` to `up` to get three visible log windows instead of hidden
processes: `./run-local.ps1 up -Windows`.

## Commands

| Command | What |
| --- | --- |
| `bootstrap` | one‑time: download portable PG + Redis into `.localstack`, `initdb`, create db `protrix` |
| `setup` | venv + `pip install` (contracts+api+worker) + `npm ci` + `alembic upgrade head` + seed |
| `setup -SkipInstall` | just migrate + seed (skip pip/npm) |
| `up` / `up -Windows` | start infra (portable) + the three app processes |
| `status` | ports + health JSON |
| `down` | stop everything the script started; **keeps** the database |
| `reset` | `alembic downgrade base` → `upgrade head` → re‑seed |
| `teardown` | `down` + delete `.localstack` (full reverse) |

## Ports

| Service | URL / endpoint |
| --- | --- |
| api | <http://localhost:8000> (`/health`, `/docs`) |
| worker health | <http://localhost:8100/health> |
| web | <http://localhost:3000> |
| PostgreSQL | portable `localhost:55432` · system `localhost:5432` — db/user/pass `protrix` |
| Redis | portable `localhost:6399` · system `localhost:6379` |

Logs (hidden mode): `.run-local\logs\protrix-{api,worker,web}.log`.
Portable infra logs: `.localstack\postgres.log`, `.localstack\redis.log`.

## Integration tests against the running stack

```powershell
.\.venv\Scripts\python -m pip install -r tests\requirements.txt
$env:PROTRIX_DATABASE_URL = "postgresql+psycopg://protrix:protrix@localhost:55432/protrix"  # portable
$env:PROTRIX_REDIS_URL    = "redis://localhost:6399/0"
.\.venv\Scripts\python -m pytest tests -q
```

`test_worker_restart.py` is skipped without Docker (it restarts a container);
the slice, duplicate and executor‑timeout tests run.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `bootstrap` download slow/fails | re‑run it — the `.zip`s are cached in `.localstack\_dl` and skipped if present |
| `port 8000/3000 already in use` | free the port, or edit `$e` in `run-local.ps1` and the `uvicorn --port` / `next dev` line |
| web shows "dev login failed" | the `api` process isn't ready — `./run-local.ps1 status`, check `.run-local\logs\protrix-api.err.log` |
| worker log shows it exiting | run `./run-local.ps1 setup` (schema/seed missing) |
| want it all gone | `./run-local.ps1 teardown` then delete `.venv` and `web\node_modules` |

## Fully manual equivalent (system Postgres/Redis)

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e contracts/python -r api/requirements.txt -r worker/requirements.txt
cd web; npm ci; cd ..

$env:PROTRIX_DATABASE_URL = "postgresql+psycopg://protrix:protrix@localhost:5432/protrix"
$env:PROTRIX_REDIS_URL    = "redis://localhost:6379/0"
$env:PROTRIX_APP_ENV = "local"; $env:PROTRIX_WORKER_HEALTH_PORT = "8100"; $env:PROTRIX_API_URL = "http://localhost:8000"

cd api;    .\..\.venv\Scripts\python -m alembic upgrade head
           .\..\.venv\Scripts\python -m app.seed
           .\..\.venv\Scripts\python -m uvicorn app.main:app --port 8000     # terminal 1
cd worker; .\..\.venv\Scripts\python -m app.main                             # terminal 2
cd web;    npm run dev                                                       # terminal 3
```
