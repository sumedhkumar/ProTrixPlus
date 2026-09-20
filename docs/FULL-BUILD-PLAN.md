# ProTrixPlus — full build plan (PRD-aligned)

Unifies two things that were previously two separate conversations into one
sequence: the UI build-out (the "My Trading Terminal" dashboard prototype)
and the PRD's functional/business requirements (entitlements, billing,
referrals). They were always the same underlying work seen from two angles —
every PRD milestone below has a corresponding UI surface, and every UI tab in
the Phase 0 prototype is a placeholder for a specific PRD milestone.

Status of each phase is marked; only Phase 0 is built so far, and it is
pending your review before anything else proceeds.

**Signal source, confirmed:** this platform uses TradingView's real Alert
mechanism (the admin's own TradingView account, paid plan) delivering to a
production webhook — not the `TradingView-MT5-Bridge` Chrome-extension/DOM-
scraping approach explored earlier in this conversation. That thread is
closed for this product; it doesn't appear anywhere below.

---

## Open questions that gate specific phases (answer before those phases start)

The PRD itself leaves these unanswered (Sections 2, 6, 7, 9, 10, 11, 13, 14
were present as headers only, with no content, in what you pasted):

1. **MT5 integration method** — native `MetaTrader5` Python package (Windows
   terminal per account, per `docs/LOCAL-MT5.md`) vs. MetaApi.cloud (already
   ProTrixPlus's own decided direction per its `ADR-001`)? Gates **Phase 5**.
2. **Alert/exit contract.** How does a TradingView EXIT signal represent
   *which* open position to close? This is a real, already-documented gap —
   `docs/TRADINGVIEW-MT5.md` states the current adapter "rejects management
   commands until a stable `position_ref` mapping is provided" and warns not
   to use a generic order-fill message for exits. Distinct from question #3
   below (this is about the signal's own format; #3 is about admin-initiated
   deactivation). Gates **Phase 1, Phase 5**.
3. **Close policy when admin turns a strategy OFF.** PRD 4.3 says OFF blocks
   new entries but defers "handling of already-open positions" to a
   separately configured policy that isn't defined. Gates **Phase 5**.
4. **Settlement formula specifics** — gross vs. net-of-fees P&L, per-trade vs.
   daily-aggregate, and whether 10%/20% is per-strategy admin-configured or a
   platform default. Gates **Phase 7**.
5. **Payment/collection workflow for MVP.** PRD 3.2 explicitly defers
   "self-service payment gateway automation" to a later phase — my working
   assumption is that MVP entitlement is admin-granted manually (an admin
   flips a client's access on after receiving payment out-of-band). Confirm
   or correct this — it changes Phase 2's and Phase 7's API/UI shape. Gates
   **Phase 2, Phase 7**.
6. **Referral bonus rules** — trigger condition (signup vs. first payment),
   bonus amount/percentage, payout mechanism. Gates **Phase 8**.

One more thing worth flagging explicitly: **the AI Copilot / Market Radar /
Kelly sizing / chat features are not in the PRD's functional requirements at
all** — they came from the UI mockup, not the PRD. They're real, substantial
scope (external market-data feed, LLM integration) that the PRD's MVP
definition doesn't ask for. I've kept them as a distinct phase (Phase 9) so
they can be explicitly included or dropped from MVP without disturbing the
PRD-required phases.

---

## Phase 0 — Static UI prototype
**Status: built, in `prototype-protrix/`, pending your review.**

All-mock dashboard matching the reference design. No backend, no auth, no
shared code with `web/`.

---

## Phase 1 — TradingView signal ingestion
**PRD refs:** 1, 3.1, 4.2 ("Signal-to-Execution Flow" — section present but
empty in what was pasted; needs content), 4.3 step 3 ("admin maps TradingView
alert identifiers to the strategy"), 5.4 ("TradingView Signal Ingestion" —
also present but empty), 12 (acceptance: a valid authenticated alert produces
exactly one eligible execution attempt per entitled active client; duplicate
alerts are visible and never produce silent duplicate orders).

**What already exists and is reusable:** the webhook receiver itself
(`/webhook/tradingview/{token}`), envelope schema validation, and
`signal_id`/`idempotency_key`-based dedup — built and tested in the earlier
S0 skeleton work.

**What's new for this product:**
- Admin-facing workflow to map a TradingView alert's identifying fields to a
  specific strategy record (PRD 4.3 step 3) — no such admin UI exists today.
- Production-grade public delivery for the webhook. The only public-ingress
  path built so far (`infra/scripts/tradingview_gateway.py` + a `cloudflared`
  quick tunnel) was explicitly flagged earlier as dev-only: the tunnel
  hostname rotates on every restart, which breaks any TradingView alert
  pointed at it. This needs a stable domain + TLS + reverse proxy — the same
  gap as Phase 11 below, but this phase is the first thing that actually
  requires it to be solved.
- The exit/close alert contract (open question #2) — needed before any
  exit-type signal can be trusted to close the right position.

---

## Phase 2 — Auth + entitlement foundation
**Unblocks:** everything else. **PRD refs:** 3.1, 5.1, 5.3, 5.4, 5.5, 12
(acceptance criteria: "expired/non-entitled client does not receive a trade").

- Real client signup/login, distinct from the current mock USER/SUPER_ADMIN
  picker. Admin role stays separate (maps reasonably well to existing
  `SUPER_ADMIN`).
- Extend `strategies` table: `description`, `timeframe`, `price`,
  `profit_share_percent`, default `base_lot`, allowed multiplier set
  (constrained to 1X/2X/3X, not a free decimal as today).
- Extend `strategy_assignments` with entitlement fields: `purchased_at`,
  `expires_at`, `payment_status`.
- Replace the worker's placeholder eligibility check (currently hardcoded
  "always ACTIVE" per the README) with real logic: entitled + strategy ON +
  client enabled + (later) MT5 connected.
- UI: wire the header's Execution Engine pill and the "Active Subscriptions"
  card to real auth/data instead of Phase 0's mock values.

**Depends on:** open question #5.

---

## Phase 3 — MT5 connection layer
**PRD refs:** 3.1, 4.1 (steps 2–3), 5.2.

- New `mt5_connections` table: user, broker/server, login, connection
  status (Connected/Disconnected/Error), last-checked timestamp.
- Real `CredentialVault` backend (currently a stub — this was already
  flagged as a hard prerequisite before any real credential touches the
  system).
- UI: wire the "MT5 Balance" card's connection badge to a real status check.
  The balance figure itself stays mock until Phase 5.

---

## Phase 4 — Strategy Marketplace
**PRD refs:** 3.1, 4.1, 4.3, 6, 7, 12 (acceptance: admin can create/configure
a strategy and turn it ON/OFF; client can select an allowed multiplier and
see the effective lot).

- Admin: create/edit strategy catalog entries (all Phase 2 fields), global
  ON/OFF toggle, per-client enable/disable (the `strategy_assignments.status`
  column already supports this).
- Client: browse available strategies (price, billing model, timeframe,
  status), activate, choose 1X/2X/3X with a live effective-lot preview
  before saving.
- UI: replaces the current "coming in a later phase" placeholder on the
  Strategy Marketplace tab with real content.

---

## Phase 5 — Real MT5 execution, entitlement-gated
**PRD refs:** 4.2, 5.2, 5.5, 12 (acceptance: one eligible execution attempt
per entitled active client; OFF prevents new trades; admin override changes
effective lot without affecting other clients).

- Real execution adapter, wired to Phase 2's entitlement gate — every
  execution attempt must pass the real eligibility check, not the
  placeholder.
- Position sizing: `base_lot × multiplier`, respecting admin per-client
  caps/overrides.
- Exit signals resolve to the correct open position per open question #2's
  answer; strategy OFF blocks new entries, with already-open positions
  handled per open question #3's answer.
- UI: MT5 Balance/Account Equity/Free Margin cards go from mock to real
  numbers once the adapter reports real account data.

**Depends on:** open questions #1, #2, #3.

---

## Phase 6 — Trade history & P&L
**PRD refs:** 5.6, 12 (acceptance: client sees own trades, admin sees all;
trade reconciles to an MT5 ticket/deal + correct strategy/client id).

- Extend `executions` with price/PnL fields (currently has none at all).
- Client view (own trades only) + admin view (all trades) — the existing
  `/api/v1/executions` route and `ExecutionsTable` component are the
  starting point, need entitlement/role-based scope review.
- UI: replaces the Execution History tab's placeholder; makes the "Realized
  Strategy P&L" and "Audited" badge on the terminal real instead of mock.

---

## Phase 7 — EOD settlement & billing
**PRD refs:** 3.1, 5.7, 12 (acceptance: EOD settlement calculates the
configured 10%/20% fee from eligible realized profit and stores the
calculation).

- New `settlements` table + a daily batch job computing profit share per
  the resolved formula (open question #4).
- Payment/collection workflow per open question #5's resolution.
- UI: replaces the EOD Settlement Ledger tab's placeholder.

**Depends on:** open questions #4, #5.

---

## Phase 8 — Referrals & renewals
**PRD refs:** 3.1, 4.1 (step 8, implied), 5.8, 12 (acceptance: referral code
links to a referred paid client with a traceable bonus status; expired
strategy access can be renewed).

- New tables: referral codes, referral attribution, reward ledger — actual
  business rules per open question #6.
- Renewal workflow for expiring `strategy_assignments` entitlements.
- UI: replaces the Referrals & Rewards tab's placeholder.

**Depends on:** open question #6.

---

## Phase 9 — AI Copilot (not in the PRD — flagged separately)
**Source:** UI mockup only, not a PRD functional requirement.

- Real market-data feed integration (price/volatility per symbol) to
  replace Phase 0's mock Market Radar cards.
- Kelly Criterion sizing math, using Phase 6's real P&L/variance data.
- "Ask Copilot" chat — LLM backend integration + conversation storage.

**Recommend confirming whether this is in MVP scope at all** before
scheduling it relative to Phases 1–8.

---

## Phase 10 — Operational safety & monitoring
**PRD refs:** 3.1, 11 ("Error Handling and Safety Scenarios" — section
present but empty in what was pasted; needs content), 12 (acceptance:
duplicate alerts, disconnected MT5, and broker rejections are visible and
never produce silent duplicate orders).

- Admin-facing visibility into duplicate-signal rejections, MT5 disconnects,
  broker rejections (signal/order dedup already exists at the data layer —
  this phase is about surfacing it, not building it from scratch).
- Alerting for pipeline health (ties to the "Execution Engine: Active"
  status pill actually meaning something).

---

## Phase 11 — Production hardening
**PRD refs:** 10 ("Non-Functional Requirements" — present but empty; needs
content, especially around the "up to 100 client users" target from 1.1).

- Real secrets management, stable hosting/TLS, DB backups/replication —
  these are the same gaps identified in the earlier infrastructure-focused
  production-readiness discussion, now tied to specific PRD-driven urgency
  (real client money, real broker credentials). Also the actual fix for
  Phase 1's public-ingress gap.

---

## Explicitly deferred (per the PRD's own Section 3.2, not re-litigated here)

Multiple MT5 accounts per client, advanced risk controls (max daily loss,
equity stop, drawdown circuit breaker), self-service payment gateway
automation, multi-level referral/affiliate dashboards, push/email/WhatsApp
notifications, advanced performance analytics, mobile apps. The PRD already
scoped these out of MVP — listed here only so nothing gets silently assumed
in-scope later.
