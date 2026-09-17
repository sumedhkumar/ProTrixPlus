# Changes in this branch

Snapshot of everything built on `feature/prototype-protrix-ui` beyond the initial S0
skeleton (`f5d9ac5`). Real functionality is wired end-to-end wherever a backend
exists; anywhere it doesn't yet (AI analysis, Kelly sizing, EOD settlement, MetaApi
broker connectivity), the UI says so with a `DEMO` tag rather than faking it.

## Auth & identity

- Real password auth: `POST /auth/signup`, `POST /auth/login` (`api/app/auth.py`,
  `api/app/routers/auth.py`) — PBKDF2-HMAC-SHA256, 600k iterations, stdlib only.
- `User.password_hash` column + migration.
- Login page (`web/app/login/page.tsx`) rewritten: real signup/login form, plus the
  legacy mock USER/SUPER_ADMIN dev-identity buttons kept for quick testing.

## Strategy marketplace & entitlements

- `api/app/services/marketplace.py` (new): strategy catalog CRUD, admin
  grant/revoke entitlements, client-facing multiplier selection with a real
  effective-lot preview (`POST /me/assignments/preview-lot`, shared
  `protrix_contracts.money.compute_lot` — same formula the worker actually trades
  with, so the preview can't drift from execution).
- `api/app/routers/admin.py`: strategy catalog endpoints, entitlement
  grant/override (careful `exclude_unset` handling so "omitted" and "explicit
  null" `expires_at` are distinguished), ops-summary, MT5 connections list.
- New DB fields: `Strategy.description/symbol/timeframe/price/profit_share_percent
  /base_lot`, `StrategyAssignment.purchased_at/expires_at/payment_status`,
  `Execution.entry_price/exit_price/realized_pnl`.
- `web/components/StrategyMarketplaceCard.tsx`: exposure-multiplier selector with
  a live "Projected Execution Lot Sizing" preview (real math via the preview
  endpoint), a real "Update Sizing" commit, and an AI Regime Fitness / Kelly
  panel — explicitly tagged `DEMO`, since no real regime model exists. The
  "Activate & Route to MT5" button for un-granted strategies is disabled with an
  explanatory tooltip rather than faking a checkout flow (this MVP is
  admin-granted access only, no payment gateway).

## MT5 connection

- `Mt5Connection` model + migration (never stores a password, by design).
- `api/app/services/mt5_connection.py`: set/check/disconnect a client's broker
  connection. `check_connection` honestly reports `PENDING` (not `CONNECTED`)
  since no MetaApi.cloud API key is configured in this deployment.
- `web/components/Mt5ConnectionModal.tsx` + `Mt5BalanceCard.tsx`: two-tab
  "MetaTrader 5 Account Bridge" modal (Connection Setup / How This Will Work),
  replacing the old inline card. Real PUT/check/DELETE calls; the investor-token
  field is visibly marked as not-yet-wired (no credential vault exists yet).

## Execution visibility

- `read_models.list_executions()` now also returns `action` (the real
  BUY/SELL/CLOSE from the originating `Signal`, not just the coarser
  `command_target`) — fixes a real bug where the "Side" column's color logic
  never matched any real value and always rendered red.
- `web/components/ExecutionHistoryTable.tsx`: strategy filter dropdown, a
  derived (not fabricated) `CLOSED` status for filled executions that have an
  exit price, and a real client-side "Export CSV Audit" of the currently
  filtered rows.
- `web/components/ExecutionEngineStatus.tsx`: hover/click diagnostics panel on
  the header's "Execution Engine" pill — real webhook path, real idempotency
  status, and role-scoped real bridge/signal counts (a plain user sees only
  their own MT5 bridge status; an admin sees the real system-wide counts via
  `ops-summary` and `admin/mt5-connections`).

## TradingView integration (real, not the old TradingView-MT5-Bridge repo)

- `api/app/routers/webhook.py`'s existing `POST /webhook/tradingview/{token}`
  path-token route (already normalizes TradingView's lowercase
  `buy`/`sell` → `BUY`/`SELL` and bare `"15"` → `"15m"`) is the live integration
  point — verified end-to-end against a real TradingView alert (`SAIYAN OCC
  Strategy R5.41`), including over a public ngrok tunnel.
- Registered the `saiyan-occ-r541` strategy in the catalog and granted it, so
  real alerts now produce real `FILLED` executions instead of just being logged
  with `0 client(s)` dispatched.

## Data-loss root cause and fixes

Two real incidents this session, both now fixed at the code level (not just
documented):

1. `make reset` ran `docker compose down -v` with no confirmation and no backup.
   Fixed: `make reset` now auto-runs a backup and requires typing `yes`.
2. **The actual root cause**: `api/tests/conftest.py`'s `db_engine` fixture runs
   `metadata.drop_all()` on whatever `PROTRIX_DATABASE_URL` points at. Running the
   test suite with that env var pointed at the local dev stack's port (`55432`)
   wiped every real account, strategy, and execution — twice. Fixed: the fixture
   now hard-refuses (`pytest.exit`) to run against port `55432` unless
   `PROTRIX_ALLOW_TEST_DB_WIPE=1` is explicitly set.
3. New `infra/scripts/backup-db.sh` / `restore-db.sh` (real `pg_dump -Fc` /
   `pg_restore`, keeps the last 10 backups) plus `make backup` / `make restore`.
   `infra/backups/*.dump` is gitignored.

## Other fixes

- `web/lib/proxy.ts`: a 204 No Content response from the API crashed the
  Next.js route handler (`Response` rejects a body-bearing init with a
  null-body status) — the MT5 "Disconnect" button was silently 500ing. Fixed.
- `.appshell-header`'s `backdrop-filter` creates a CSS containing block for
  `position: fixed` descendants — both the Simulate-Signal modal and the new
  Execution Engine popover are rendered as DOM siblings of `<header>`, not
  children, to avoid being clipped to the header's box.
- `infra/.env`: `PROTRIX_POSTGRES_PORT` pinned to `55432` everywhere so
  `docker compose up` can't accidentally recreate the postgres container over a
  port mismatch.

## Not done / explicitly deferred

- Real MetaApi.cloud broker connectivity (currently `PENDING`, not `CONNECTED`).
- EOD profit-share settlement math, referral rules, Kelly sizing, AI Copilot
  analysis — all still demo data, clearly tagged.
- Closing/managing an existing position from a TradingView alert: this MVP's
  `CLOSE` action requires an explicit `position_ref`, which TradingView's
  generic "order fills" alert can't supply. Every alert is currently treated as
  a fresh entry.
