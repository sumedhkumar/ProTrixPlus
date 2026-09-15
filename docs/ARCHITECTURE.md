# Protrixplus architecture (MVP)

The MVP is a **local, demo-first trading control plane**: durable
TradingView-compatible signals, server-enforced eligibility/risk, managed
position attribution, a mock Docker executor, and an optional native Windows
MT5 demo adapter. MetaApi remains a later adapter implementation; no paid
MetaApi account or credential is required today.

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
| `worker/` | Outbox relay, signal fan-out, subscription/wallet/account/risk eligibility, managed-position ownership, mock/native-MT5 execution + reconciliation, catch-up sweep. |
| `web/` | Next.js App Router: `/dashboard` (USER portfolio) and `/admin` (SUPER_ADMIN operations), with local dev sign-in. |
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
| No duplicate intent | DB unique constraint `uq_order_intents_signal_op_key`; fan-out upserts by user, strategy, signal, command target, and execution key. A directional reversal uses each mapped opposite position reference as its close key. |
| Idempotent acceptance | `uq_signals_idempotency_key` + fast-path lookup + `IntegrityError` fallback. Repeated id → 200 `duplicate:true`, no new rows. Traced by `tests/test_duplicate_signal.py`, `api/tests/test_ingest.py`. |
| Decimal money / lots | `Numeric` columns everywhere; `contracts/protrix_contracts/money.py` (`ROUND_HALF_EVEN` for money, `ROUND_DOWN` for lots); wire values are strings; api parses JSON with `parse_float=Decimal`. |
| UTC timestamps | `timestamptz` columns; `ALTER DATABASE … SET timezone UTC`; app writes `datetime.now(UTC)`. |
| No secret in logs | `SecretRedactionFilter` on the root logger in api + worker; `SecretStr` config; `/health` returns no secrets. |
| UNKNOWN ≠ FAILED | Lifecycle state machine: `UNKNOWN` only transitions to `RECONCILED`; there is **no** edge that re-sends. A periodic worker loop reconciles unknown entries with `sync_positions`, never `place`. Unknown management commands remain visible for operator review because a snapshot cannot prove a lost close/modify result. |

## Transactional outbox

api writes an `outbox` row in the same transaction as the `signals` row. The
worker's relay loop moves PENDING rows to the Redis stream and marks them
PUBLISHED — the row stays in Postgres, so Redis is never the only record. The
consumer uses a Redis Streams consumer group; on every tick it `XAUTOCLAIM`s
messages stranded by a dead consumer before reading new ones, and only `XACK`s
after fan-out commits. Combined with idempotent fan-out and a startup catch-up
sweep, a worker crash/restart loses nothing and duplicates nothing.

## Extension points

| Seam | File | Replacement |
| --- | --- | --- |
| `IdentityProvider` | `api/app/identity/base.py` | real OIDC provider |
| `ExecutionAdapter` | `worker/app/adapters/base.py` | `MetaApiExecutionAdapter` (ADR-001) |
| `CredentialVault` | `api/app/vault/base.py` | rotating short-TTL secret backend |
| `evaluate()` eligibility | `worker/app/eligibility.py` | funding / drawdown / schedule gating |
| `compute_lot()` | `worker/app/sizing.py` | full risk-aware sizing |
| webhook auth | `api/app/security.py::webhook_authorized` | signed TradingView verification |

## Still deliberately deferred

MetaApi credentials and paid transport, production identity, a real credential
vault, broker-specific reconciliation proof for management timeouts, and
live-account enablement. See [MVP-HANDOFF.md](MVP-HANDOFF.md) for the
parallel-work split and MetaApi cutover sequence.
