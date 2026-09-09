# See the S0 skeleton working — a 5‑minute walkthrough

The stack runs locally with no Docker via `run-local.ps1` (portable mode). This
guide shows what to do and what you should see.

> All commands are PowerShell, run from the repo root
> `C:\Users\HP\Desktop\Protrix plus`.
> Portable tools live under `.localstack\`:
> `redis-cli = .\.localstack\redis\Redis-8.10.1-Windows-x64-msys2\redis-cli.exe`.

---

## 0. Make sure it's up

```powershell
./run-local.ps1 status
```

Expected — five `LISTEN`, api + worker `status=ok`:

```
mode: portable (.localstack)
  postgres  port 55432  LISTEN
  redis     port 6399   LISTEN
  api       port 8000   LISTEN  HTTP 200 status=ok
  worker    port 8100   LISTEN  HTTP 200 status=ok
  web       port 3000   LISTEN  HTTP 200
```

If anything is `--`, run `./run-local.ps1 up`. First time ever: `./run-local.ps1
bootstrap` then `./run-local.ps1 setup` then `up` (see `docs/RUN-LOCAL.md`).

---

## 1. Open the User dashboard

Browse to **<http://localhost:3000>** → you're redirected to `/login`.

Click **“Sign in as USER”**. You land on **`/dashboard`** (the *User dashboard
shell*). You should see:

- top bar: `Alice Trader · USER`
- **Signals** panel — *“No signals yet.”*
- **Executions** panel — *“No executions yet.”*

That's the shell reading from the api with a fake USER identity. Nothing has
happened yet.

---

## 2. Fire a mock TradingView signal

In a terminal:

```powershell
.\.venv\Scripts\python infra\scripts\simulate_signal.py --signal-id demo-1
```

Expected:

```
[1/1] 202 {"accepted": true, "duplicate": false, "signal_id": "demo-1",
           "signal_row_id": "....", "payload_hash": "sha256:...."}
```

What just happened, in order:

1. the script POSTed a frozen **v1.0 webhook envelope** to
   `api /webhook/tradingview` with the shared‑secret header;
2. api validated it against `contracts/schemas/webhook_envelope.v1.json`,
   computed the canonical **payload hash**, and wrote the `signals` row **plus an
   `outbox` row in one transaction — before returning `202`**;
3. the **worker** relayed the outbox row to a Redis stream, fanned out to the
   **3 seeded users**, created **one `order_intent` per user**, and ran each
   through the **mock executor** → lifecycle
   `RECEIVED → INTENT_CREATED → QUEUED → DISPATCHED → ACKNOWLEDGED → FILLED`.

---

## 3. Watch it appear on the dashboard

Back in the browser, **refresh `/dashboard`** (give it 2–3 s). Now:

- **Signals** — one row: `demo-1 · trend-rider@2025.09 · BUY · EURUSD · 15m`,
  `intents 3`, a truncated `sha256:…` hash.
- **Executions** — **one row** (this is a USER, so only *Alice's* execution):
  `demo-1 · Alice Trader · EURUSD · ENTRY · 1.00 · mock · FILLED`, a `ticket`,
  a `deal`, `reconciles 0`, and `latency ms (disp/ack/fill)`.

`state` is green (`FILLED`). Lot is the exact decimal `1.00`.

---

## 4. Look at the same data as SUPER_ADMIN

Click **Sign out**, then **Sign in as SUPER_ADMIN** → you land on **`/admin`**
(the *Super Admin dashboard shell*). Now you see:

- **Users** — Alice, Bob, Carol (`USER`), Root Admin (`SUPER_ADMIN`), with
  assignment counts.
- **Strategy assignments** — 3 rows: `master_lot 1.00`, `multiplier 1.0000`,
  bounds `0.5000–2.0000`, `ACTIVE`.
- **Signals** — same `demo-1`.
- **Executions** — **all three** now (Alice, Bob, Carol), each `FILLED` with its
  own ticket/deal.

---

## 5. Prove the guarantees (optional, ~2 min)

### Idempotent acceptance — a repeat creates nothing

Post the **exact same bytes** twice:

```powershell
1..2 | ForEach-Object {
  curl.exe -s -X POST http://localhost:8000/webhook/tradingview `
    -H "X-Webhook-Token: dev-webhook-token-change-me" `
    -H "Content-Type: application/json" `
    --data-binary "@tests/sample_signals/buy.json" `
    -w " [%{http_code}]`n"
}
```

Expected: first `[202]` `"duplicate": false`, second `[200]` `"duplicate":
true`. The dashboard still shows **3** executions for `sample-buy-1`, not 6.

### Executor timeout → UNKNOWN → reconciliation (never a blind retry)

```powershell
.\.localstack\redis\Redis-8.10.1-Windows-x64-msys2\redis-cli.exe -p 6399 set mock_exec:arm_timeout 1
.\.venv\Scripts\python infra\scripts\simulate_signal.py --signal-id timeout-1
```

Refresh `/admin`. Among the 3 executions for `timeout-1`, **one shows
`reconciles 1`** and still ends `FILLED`. Its audit trail went
`DISPATCHED → UNKNOWN → RECONCILED → FILLED` — the mock “lost the response”, the
worker asked the broker what really happened and resolved it, **without
re‑sending the order**.

### A USER cannot reach the admin area

While signed in as USER, type **<http://localhost:3000/admin>** in the address
bar. You're bounced straight back to `/dashboard` (edge middleware), and the api
would return `403` for the admin endpoints anyway.

---

## 6. Poke the API directly (optional)

- Interactive docs: **<http://localhost:8000/docs>**
- Health with dependency checks: `curl http://localhost:8000/health`
- Get a token and read the lists:

```powershell
$tok = (Invoke-RestMethod -Method Post http://localhost:8000/dev/login `
        -ContentType application/json -Body '{"role":"SUPER_ADMIN"}').access_token
Invoke-RestMethod http://localhost:8000/api/v1/signals    -Headers @{Authorization="Bearer $tok"}
Invoke-RestMethod http://localhost:8000/api/v1/executions -Headers @{Authorization="Bearer $tok"}
```

---

## 7. Logs

Hidden‑process logs (JSON lines):

```
.run-local\logs\protrix-api.err.log
.run-local\logs\protrix-worker.err.log
.run-local\logs\protrix-web.log
```

`Get-Content .\.run-local\logs\protrix-worker.err.log -Tail 20 -Wait` follows the
worker as signals flow.

---

## 8. Stop / clean up

```powershell
./run-local.ps1 down        # stop api + worker + web + portable pg/redis (keeps data)
./run-local.ps1 reset       # wipe DB -> re-migrate -> re-seed (clean dashboards)
./run-local.ps1 up          # start again
./run-local.ps1 teardown    # stop + delete .localstack  → machine exactly as before
```
