# Protrixplus — S0 mock skeleton

A stable **local** foundation: fake users, mock TradingView signals, a mock MT5
executor. **Zero paid infrastructure, zero real credentials.** Everything
external is a local mock or a stub adapter behind an interface.

This milestone (S0) is the skeleton only — not business features.

```
web (Next.js)  ─┐
                ├─ api (FastAPI) ─ PostgreSQL ─┐
simulator ──────┘        │  outbox row          │  source of truth
                         ▼                      │
                       Redis stream ── worker (Python) ── MockExecutionAdapter
                                        fan-out · eligibility · intents · lifecycle
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and
[docs/adr/ADR-001](docs/adr/ADR-001-metaapi-execution-transport.md).

## Prerequisites

- Docker + Docker Compose v2
- (for local dev outside Docker) Python 3.12+, Node 22+

## Run the whole stack

### Unix / macOS

```bash
cp infra/.env.example infra/.env
docker compose -f infra/docker-compose.yml --env-file infra/.env up --build -d
```

### Windows (PowerShell)

```powershell
Copy-Item infra\.env.example infra\.env
docker compose -f infra/docker-compose.yml --env-file infra/.env up --build -d
# or:  ./dev.ps1 up
```

Then:

```bash
curl -fsS localhost:8000/health      # api    -> {"status":"ok",...}
curl -fsS localhost:8100/health      # worker -> {"status":"ok",...}
curl -fsS localhost:3000/login       # web    -> 200
python infra/scripts/simulate_signal.py
```

Open <http://localhost:3000>, sign in as **USER** or **SUPER_ADMIN** (mock
identity, no password), and watch the signal and its execution appear.

Back up real data any time: `make backup` (writes to `infra/backups/`,
restore with `make restore`). Full reset (wipes every account/signal - auto
backs up first, asks for confirmation): `make reset`. Don't run
`docker compose down -v` directly - it skips both safety steps.

### No Docker?

`docs/RUN-LOCAL.md` + `run-local.ps1` run the stack against a natively-installed
PostgreSQL 16 and Redis 7:

```powershell
./run-local.ps1 setup   # venv + deps + create db + migrate + seed
./run-local.ps1 up      # redis (if needed) + api + worker + web
./run-local.ps1 status
```

## The mock signal slice

1. `infra/scripts/simulate_signal.py` POSTs a frozen v1.0 envelope to
   `api /webhook/tradingview` (shared-secret header).
2. api validates against `contracts/schemas/webhook_envelope.v1.json`, computes a
   canonical payload hash, and writes `signals` + an `outbox` row **in one
   transaction, before returning 2xx**. Malformed → 422, unauthorized → 401,
   duplicate `signal_id` → 200 `duplicate:true` with no new rows.
3. worker's relay moves the outbox row to a Redis stream; the consumer fans out
   to every seeded USER, runs the placeholder eligibility check (always ACTIVE),
   and creates **exactly one** `order_intent` per
   `(user, strategy, signal, command_target)` — enforced by a DB unique
   constraint.
4. `MockExecutionAdapter` returns deterministic broker ids; the execution walks
   `RECEIVED → INTENT_CREATED → QUEUED → DISPATCHED → ACKNOWLEDGED → FILLED`.
   A simulated timeout goes `DISPATCHED → UNKNOWN → RECONCILED → FILLED` — never
   a blind re-send.
5. Both dashboards render the stored signal + execution status.

## Local checks (no Docker)

```bash
make install         # or: ./dev.ps1 install
make ci-local        # lint + typecheck + all unit tests
```

Per package:

| Package | Commands |
| --- | --- |
| `contracts/python` | `pip install -e "contracts/python[dev]"` · `ruff check .` · `ruff format --check .` · `mypy protrix_contracts` · `pytest` |
| `api` | `pip install -e contracts/python -r api/requirements-dev.txt` · `cd api` · `ruff check . && ruff format --check .` · `mypy app` · `alembic upgrade head` · `alembic check` · `pytest` |
| `worker` | `pip install -e contracts/python -r worker/requirements-dev.txt` · `cd worker` · `ruff check . && ruff format --check .` · `mypy app` · `pytest` |
| `web` | `cd web` · `npm ci` · `npm run lint` · `npm run typecheck` · `npm test` · `npm run build` |

`pytest` tests tagged `dbtest` / `integration` auto-skip when PostgreSQL/Redis or
the composed stack are unreachable; CI always runs them.

## Integration + e2e (needs the stack running)

```bash
pip install -r tests/requirements.txt
PROTRIX_COMPOSE_FILE=infra/docker-compose.yml pytest tests -q     # slice, duplicate, restart, timeout

cd web && npx playwright install chromium && npx playwright test  # dashboard e2e
```

## CI

One workflow — [.github/workflows/ci.yml](.github/workflows/ci.yml) — runs lint,
format, type-check, unit tests, `alembic check`, `next build`, then brings the
compose stack up and runs the integration suite + Playwright e2e. No external
secrets.

## Security posture (S0)

- No real secrets, broker/MT5 libraries, live alerts, or cloud services anywhere.
- Config secrets are `SecretStr`; a root-logger redaction filter scrubs known
  secret substrings from every log line in api + worker.
- `CredentialVault` is a stub returning fake, key/value-separated material behind
  a short-lived scoped handle; plaintext is never returned to api/web/logs.
- Every dependency is pinned; lockfiles are committed.
