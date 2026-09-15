# MVP handoff and parallel-work boundaries

## What is live now

The local MVP accepts a durable TradingView-compatible signal, validates and
stores it, relays it through Redis, and fans it out into server-owned order
intents. The Docker worker uses the mock adapter. A separately started native
Windows worker can execute against one explicitly configured **demo** MT5
account; each account has its own Redis consumer group.

New entries require an active subscription, positive rent-wallet balance,
active account, no safety block, an allowed symbol, a lot limit, and an open
position limit. Close, partial-close, SL/TP modification, and emergency-close
commands are resolved only through `managed_positions`; a webhook never gets to
choose a broker ticket. An exit is still permitted when entry gates are blocked.

The future MetaApi integration remains an adapter replacement. No MetaApi token
or paid account is required for this MVP.

## Ownership split

| Owner | Primary paths | May change | Must coordinate before changing |
| --- | --- | --- | --- |
| Data/contracts | `contracts/python/`, `api/alembic/` | models, constraints, migrations, schema tests | any existing model/constraint or migration revision |
| API/control plane | `api/app/routers/`, `api/app/services/` | authenticated user/admin APIs, audit records, seed data | payload contract, security dependencies, database changes |
| Execution/worker | `worker/app/`, `infra/scripts/` | eligibility, risk checks, adapters, relay/fanout, broker handling | `ExecutionAdapter`, lifecycle transitions, Redis group semantics |
| Web | `web/` | dashboard/admin presentation and authenticated web proxies | API response shapes and role policy |

Do not have two contributors edit the same migration, shared model, adapter DTO,
or API response contract at once. Land the contract/migration first, then API
and worker changes, then the web consumer.

## Non-negotiable invariants

- A signal and its outbox event commit before the webhook returns success.
- The database enforces one intent per `(user, strategy, signal, command target,
  execution key)` and one execution per intent. The execution key lets one
  directional reversal signal close each tracked opposite position safely.
- Numeric currency and lot values use `Decimal`/`Numeric`, never float.
- Only the worker decides whether an entry is eligible and its computed lot.
- A management alert names a source position reference; the worker maps that to
  a user- and strategy-owned broker position. It never trusts a ticket from the
  alert.
- A timeout is `UNKNOWN`, never permission to resend. Management timeouts stay
  `UNKNOWN` until broker reconciliation can prove the outcome.
- `.env` and account-profile files remain local-only. Do not log, commit, or
  paste broker passwords, tokens, or webhook path secrets.

## MetaApi cutover checklist

1. Implement `MetaApiExecutionAdapter` against `worker/app/adapters/base.py`;
   do not move eligibility, sizing, risk, or position ownership into MetaApi.
2. Add a credential reference/provider that never returns a token from an API
   response or log line.
3. Add adapter contract tests plus a MetaApi sandbox test behind an explicit
   opt-in environment flag.
4. Extend the existing periodic entry reconciliation to MetaApi. Unknown
   management commands remain operator-visible until a broker-specific proof
   mechanism can resolve them safely.
5. Migrate one demo account first, verify entry and mapped close, then promote
   accounts one at a time.

## Verification order

1. Run contract, API, worker, and web checks against an isolated test database.
2. Rebuild the Docker API/worker/web images and verify `/health`, `/portfolio`,
   `/api/v1/admin/operations`, and the dashboard.
3. For native demo execution, use the account profile with
   `run-local.ps1 mt5-worker -ProfileFile ...`; confirm worker health before
   issuing a bounded entry/close test through the local webhook simulator.
