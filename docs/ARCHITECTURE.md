# Protrixplus architecture (S0 skeleton)

S0 is a **stable local foundation**: fake users, mock TradingView signals, a mock
MT5 executor. Zero paid infra, zero real credentials. Everything external is a
local mock or a stub adapter behind an interface.

## Services

```
                 ┌──────────┐        POST /webhook/tradingview
   simulator ───▶│   api    │  (FastAPI)  validate → hash → persist → outbox
                 │          │  dashboard read APIs, mock dev identity
                 └────┬─────┘
                      │ same DB transaction
                 ┌────▼─────────────────────────────┐
                 │           PostgreSQL             │  source of truth
                 │  signals · outbox · order_intents│  constraints enforced here
                 │  executions · audit_events · …   │
                 └────┬─────────────────────────────┘
                      │ outbox relay (SELECT … FOR UPDATE SKIP LOCKED)
                 ┌────▼─────┐   XADD    ┌─────────┐
                 │  worker  │──────────▶│  Redis  │ stream protrix.signals.v1
                 │ (Python) │◀──────────│ streams │ consumer group + XAUTOCLAIM
                 └────┬─────┘  XREADGROUP└─────────┘
                      │ idempotent fan-out
                      │  1 intent  per (user, strategy, signal, command_target)
                      │  1 execution per intent  → MockExecutionAdapter
                      ▼
                 executions walk the lifecycle state machine
                 RECEIVED→INTENT_CREATED→QUEUED→DISPATCHED→ACKNOWLEDGED→FILLED
                 (timeout: DISPATCHED→UNKNOWN→RECONCILED→FILLED)

   web (Next.js) ── reads api ──▶ User shell / Super-Admin shell (role-routed)
```

## Repository layout

| Dir | What |
| --- | --- |
| `contracts/` | Frozen webhook JSON Schema (v1.0), canonical hashing, execution lifecycle, Decimal money helpers, **and** the shared SQLAlchemy models. Installed into api + worker as `protrix-contracts`. |
| `api/` | FastAPI: webhook ingress, dashboard read APIs, mock dev identity, Alembic migrations, credential-vault stub. |
| `worker/` | Outbox relay, signal fan-out, placeholder eligibility, intent creation, mock execution + reconciliation, catch-up sweep. |
| `web/` | Next.js App Router: `/dashboard` (USER shell), `/admin` (SUPER_ADMIN shell), mock sign-in. |
| `infra/` | `docker-compose.yml`, `.env.example`, postgres init, signal simulator. |
| `tests/` | Integration + e2e against the composed stack. |
| `docs/` | This file, `README.md`, `adr/`, `steps/`. |
| `.github/` | One CI workflow. |

### Why the DB models live in `contracts/`

api and worker must agree on the schema at all times, so the ORM models,
`metadata`, and session helpers are part of the shared contract package. Alembic
(in `api/`) targets `protrix_contracts.db.metadata`, which makes
`alembic check` a real model↔DB drift gate. Migration `0001` provisions the
schema straight from that metadata; later migrations are explicit `op.*` deltas.

## Invariants and where they are enforced

| Invariant | Mechanism |
| --- | --- |
| Durable before acknowledge | `api/app/services/ingest.py` commits signal + outbox row **before** the endpoint returns 2xx. Traced by `tests/test_slice_end_to_end.py` (fresh-connection read). |
| No duplicate intent | DB unique constraint `uq_order_intents_user_id_strategy_id_signal_id_command_target`; fan-out inserts `ON CONFLICT DO NOTHING`. Traced by `worker/tests/test_fanout.py`, `tests/test_worker_restart.py`. |
| Idempotent acceptance | `uq_signals_idempotency_key` + fast-path lookup + `IntegrityError` fallback. Repeated id → 200 `duplicate:true`, no new rows. Traced by `tests/test_duplicate_signal.py`, `api/tests/test_ingest.py`. |
| Decimal money / lots | `Numeric` columns everywhere; `contracts/protrix_contracts/money.py` (`ROUND_HALF_EVEN` for money, `ROUND_DOWN` for lots); wire values are strings; api parses JSON with `parse_float=Decimal`. |
| UTC timestamps | `timestamptz` columns; `ALTER DATABASE … SET timezone UTC`; app writes `datetime.now(UTC)`. |
| No secret in logs | `SecretRedactionFilter` on the root logger in api + worker; `SecretStr` config; `/health` returns no secrets. |
| UNKNOWN ≠ FAILED | Lifecycle state machine: `UNKNOWN` only transitions to `RECONCILED`; there is **no** edge that re-sends. `reconcile_unknown()` calls `sync_positions`, never `place`. Traced by `worker/tests/test_execution_lifecycle.py`, `tests/test_executor_timeout_unknown.py`. |

## Transactional outbox

api writes an `outbox` row in the same transaction as the `signals` row. The
worker's relay loop moves PENDING rows to the Redis stream and marks them
PUBLISHED — the row stays in Postgres, so Redis is never the only record. The
consumer uses a Redis Streams consumer group; on every tick it `XAUTOCLAIM`s
messages stranded by a dead consumer before reading new ones, and only `XACK`s
after fan-out commits. Combined with idempotent fan-out and a startup catch-up
sweep, a worker crash/restart loses nothing and duplicates nothing.

## Extension points (Steps 05+)

| Seam | File | Replacement |
| --- | --- | --- |
| `IdentityProvider` | `api/app/identity/base.py` | real OIDC provider |
| `ExecutionAdapter` | `worker/app/adapters/base.py` | `MetaApiExecutionAdapter` (ADR-001) |
| `CredentialVault` | `api/app/vault/base.py` | rotating short-TTL secret backend |
| `evaluate()` eligibility | `worker/app/eligibility.py` | funding / drawdown / schedule gating |
| `compute_lot()` | `worker/app/sizing.py` | full risk-aware sizing |
| webhook auth | `api/app/security.py::webhook_authorized` | signed TradingView verification |

## Not in S0 (deliberately)

Real brokers/MT5 libraries, live TradingView alerts, cloud services, IST
settlement schedule display, business features beyond the vertical slice.
