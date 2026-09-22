# ProTrixPlus — System Architecture & New-Client Onboarding Flow

This document covers two things: (1) the overall system architecture as it's
actually built and running today, and (2) the step-by-step flow a new client
goes through. Nothing below is aspirational — every component and step
described is real and deployed, and the one remaining gap is called out
explicitly rather than glossed over.

## 1. System architecture

```mermaid
flowchart TB
    subgraph client_side["Client / Admin (browser)"]
        WebApp["Next.js Web App<br/>(dashboard + admin panel)"]
    end

    subgraph tv["TradingView"]
        Strategy["Client's Pine strategy<br/>(order-fill alert)"]
    end

    subgraph protrix["ProTrixPlus backend"]
        API["FastAPI API service<br/>(auth, catalog, entitlements,<br/>webhook ingress)"]
        PG[("PostgreSQL<br/>users, strategies, entitlements,<br/>signals, executions")]
        Redis[("Redis Stream<br/>outbox relay")]
        Worker["Python Worker<br/>(fan-out, eligibility,<br/>lot sizing, execution)"]
    end

    subgraph broker["MetaApi.cloud -> Broker"]
        MetaApi["MetaApi.cloud REST API"]
        MT5["Client's real MT5 account<br/>(per-client, individually routed)"]
    end

    WebApp <-- "HTTPS (auth, REST)" --> API
    Strategy -- "Webhook: BUY/SELL signal" --> API
    API -- "write signal + outbox\n(one transaction)" --> PG
    API -- "read: catalog, entitlements,\nexecutions, balance" --> PG
    API -- "read-only balance check" --> MetaApi
    PG -- "outbox row" --> Redis
    Redis -- "signal event" --> Worker
    Worker -- "eligibility + sizing" --> PG
    Worker -- "place real order" --> MetaApi
    MetaApi --> MT5
    MetaApi -- "order result / broker error" --> Worker
    Worker -- "execution result" --> PG
```

**Key real design facts:**
- Every client's signal is routed to **their own** MetaApi account — never a shared one (per-user `Mt5Connection.metaapi_account_id`).
- The worker computes lot size and checks entitlement *before* ever calling MetaApi — MetaApi is transport only, never a decision-maker (ADR-001).
- A signal is durably written to Postgres *before* it's acknowledged — nothing is lost if the worker is down when a signal arrives.

## 2. New-client onboarding — sequence

```mermaid
sequenceDiagram
    participant C as Client
    participant A as Admin
    participant App as ProTrixPlus App
    participant MA as MetaApi.cloud
    participant TV as TradingView

    C->>App: 1. Sign up (email/password)
    A->>App: 2a. Create + price a strategy, "Approve & Enable"
    A->>App: 2b. Grant client an entitlement (lot size, multiplier bounds)
    C->>App: 3. Set exposure multiplier (within admin's bounds)
    C->>App: 4. Submit broker server + login
    Note over C,MA: 5. Self-service, direct entry - no admin, password never stored
    C->>App: 5a. Enter MT5 password, click "Connect"
    App->>MA: 5b. Create account with real login/password (forwarded, not stored)
    MA-->>App: 5c. Real account id + status
    App->>MA: 5d. Poll real account status
    MA-->>App: 5e. connectionStatus: CONNECTED
    App-->>C: 5f. Show connected status
    TV->>App: 6. Real signal (webhook)
    App->>App: Check entitlement, strategy ON, MT5 attached
    App->>MA: Place real order (client's own account)
    MA-->>App: Real ticket ID, or a real broker rejection
    App-->>C: 7. Execution History + live balance
```

## 3. Step-by-step detail

| # | Step | Who | Self-service? |
|---|------|-----|----------------|
| 1 | Sign up (email, password, display name) | Client | ✅ Yes |
| 2a | Create/price/approve a strategy in the catalog | Admin | — (admin-only by design) |
| 2b | Grant the client an entitlement (base lot, multiplier bounds) | Admin | ❌ No payment gateway yet — admin grants after being paid out-of-band |
| 3 | Client picks their exposure multiplier within the admin's bounds, with a live real lot-size preview | Client | ✅ Yes |
| 4 | Client submits their broker server + MT5 login number | Client | ✅ Yes |
| 5 | Client enters their real MT5 password directly in the app and clicks "Connect" — the password is forwarded straight to MetaApi's account-creation call and never written to our database or logs, and no admin sees it | Client | ✅ Yes — self-service, no admin involved |
| 6 | A real TradingView alert fires → webhook → entitlement + connection checked → real order placed on the client's own MetaApi-routed account | System (automatic) | ✅ Fully automatic once 1–5 are done |
| 7 | Client sees real balance/equity (tagged `LIVE`), and every order attempt in Execution History with a plain-English + technical reason if rejected | Client | ✅ Yes |

## 4. Known gaps (not hidden, not yet built)

1. **No payment gateway.** Entitlement is admin-granted, trusting that payment happened outside the app. Scoped for a later phase.
2. **Management actions (closing/modifying an existing position from a TradingView alert) aren't supported yet** — every alert is currently treated as a fresh entry. This mirrors a limitation of the underlying `position_ref` design, not something specific to onboarding.

MetaApi onboarding (step 5) used to be a manual gap — an admin had to handle the client's real MT5 password by hand. That's now resolved: the client enters their password directly in the app, which forwards it straight to MetaApi in the account-creation call — never stored, never logged. (An earlier version of this flow redirected the client to a page hosted by MetaApi itself, so the password never touched our servers at all; that's been replaced with direct in-app entry by request, trading a small amount of additional exposure - the password now transits our API for one request, in memory only - for a simpler, single-page signup experience.) An admin can still attach an existing MetaApi account ID by hand as a fallback/override, but it's no longer required for a new client.
