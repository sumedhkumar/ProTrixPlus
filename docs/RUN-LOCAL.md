# Run the S0 skeleton without Docker (Windows)

Docker Compose is the supported path (`README.md` / `infra/README.md`). This file
is the fallback: run PostgreSQL and Redis natively, then let `run-local.ps1`
start `api`, `worker`, and `web`.

## 1. Prerequisites (one-time installs)

### PostgreSQL 16

1. Download the Windows installer:
   <https://www.postgresql.org/download/windows/> (EDB installer, pick 16.x).
2. During install: keep port **5432**; set a password for the `postgres`
   superuser and remember it.
3. Confirm the service **`postgresql-x64-16`** is running
   (`services.msc`, or `Get-Service postgresql*`).

You do **not** need to create the `protrix` role/database by hand —
`run-local.ps1 setup` does it (it will ask for the `postgres` password once).

### Node.js 20–22

<https://nodejs.org/> — LTS. Verify: `node --version`, `npm --version`.

### Python 3.12+

<https://www.python.org/downloads/windows/> — check "Add python.exe to PATH".
Verify: `python --version`.

### Redis 7 (pick ONE)

Redis has no official Windows build.

**Option A — WSL (recommended)**

```powershell
wsl --install                       # then reboot if it asks
# inside the new Ubuntu shell:
sudo apt-get update && sudo apt-get install -y redis-server
```

`run-local.ps1 up` will start `redis-server` inside WSL automatically; WSL2
forwards `localhost:6379` to Windows.

**Option B — Memurai** (native Windows, Redis-compatible)

<https://www.memurai.com/get-memurai> — installs as an always-on Windows service
listening on 6379. Nothing else to do.

## 2. First run

```powershell
cd "C:\Users\HP\Desktop\Protrix plus"

# If scripts are blocked:  Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

./run-local.ps1 setup      # venv + pip + npm ci + create db + alembic upgrade + seed
./run-local.ps1 up         # starts redis (if needed) + api + worker + web in 3 windows
./run-local.ps1 status     # ports + /health
```

Then:

```powershell
python infra\scripts\simulate_signal.py     # post one mock signal
start http://localhost:3000                  # open the dashboards
```

Sign in as **USER** or **SUPER_ADMIN** (mock identity, no password) and the
signal + its execution appear.

## 3. Day-to-day

| Command | What |
| --- | --- |
| `./run-local.ps1 up` | start everything |
| `./run-local.ps1 status` | check ports + health JSON |
| `./run-local.ps1 down` | stop api/worker/web (and Redis if the script started it) |
| `./run-local.ps1 reset` | `alembic downgrade base` → `upgrade head` → re-seed |
| `./run-local.ps1 setup -SkipInstall` | just re-migrate + re-seed (skip pip/npm) |

Each service runs in its own titled PowerShell window (`protrix-api`,
`protrix-worker`, `protrix-web`) so you see logs live; closing a window stops
that service.

## 4. Ports

| Service | URL |
| --- | --- |
| api | <http://localhost:8000> (`/health`, `/docs`) |
| worker health | <http://localhost:8100/health> |
| web | <http://localhost:3000> |
| PostgreSQL | `localhost:5432` db `protrix` user `protrix` pass `protrix` |
| Redis | `localhost:6379` |

## 5. Troubleshooting

| Symptom | Fix |
| --- | --- |
| `PostgreSQL is not listening on 5432` | start the `postgresql-x64-16` service |
| `psql.exe not found` | `./run-local.ps1 setup -PgBin "C:\Program Files\PostgreSQL\16\bin"` |
| `No Redis available` | install WSL redis-server or Memurai (section 1) |
| `port 8000 already in use` | something else is on 8000 — stop it, or edit `run-local.ps1` `$SharedEnv` + the `uvicorn --port` |
| web shows "dev login failed" | the `api` window isn't up yet — wait, or check its logs |
| worker window exits immediately | run `./run-local.ps1 setup` (schema/seed missing) |
| running the integration suite | `pip install -r tests/requirements.txt` then `pytest tests -q` (the worker-restart test is skipped without Docker) |

## 6. Full manual equivalent (no script)

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e contracts/python -r api/requirements.txt -r worker/requirements.txt
cd web; npm ci; cd ..

$env:PROTRIX_DATABASE_URL = "postgresql+psycopg://protrix:protrix@localhost:5432/protrix"
$env:PROTRIX_REDIS_URL    = "redis://localhost:6379/0"
$env:PROTRIX_APP_ENV      = "local"
$env:PROTRIX_WORKER_HEALTH_PORT = "8100"
$env:PROTRIX_API_URL      = "http://localhost:8000"

# (start Redis: WSL `redis-server --daemonize yes`, or Memurai service)

cd api;    .\..\.venv\Scripts\python -m alembic upgrade head
           .\..\.venv\Scripts\python -m app.seed
           .\..\.venv\Scripts\python -m uvicorn app.main:app --port 8000     # terminal 1
cd worker; .\..\.venv\Scripts\python -m app.main                             # terminal 2
cd web;    npm run dev                                                       # terminal 3
```
