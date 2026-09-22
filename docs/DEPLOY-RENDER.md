# Free, temporary deploy: the whole stack on Render

This deploys everything to Render's free tier — api, worker, the `web`
(Next.js) frontend and Postgres — plus a free Upstash Redis, since Render
doesn't offer free Redis. There is no Vercel half any more; `render.yaml`
declares both web services, so one blueprint apply brings up the lot.

Everything here uses mock adapters/identity, same as local dev — no real
credentials needed.

Render has **no free Background Worker plan** (confirmed against the actual
dashboard — the marketing copy is misleading), so the worker runs inside the
same container as the api instead of as its own service:
`infra/render/combined.Dockerfile` builds one image that runs both
`uvicorn` (api, foreground, port 8000 — what Render health-checks) and
`python -m app.main` (worker, background, its own health port 8001) via
`infra/render/combined-entrypoint.sh`. Local dev is unaffected — that's a
separate Dockerfile from the ones `infra/docker-compose.yml` uses.

**Free-tier caveats (fine for a temporary demo, not for anything long-lived):**
- `protrixplus-api` spins down after ~15 min idle; the next request wakes it
  up (10-50s cold start, and it restarts the worker loop too since they're in
  the same container). `protrixplus-web` spins down the same way, so a cold
  visit can pay both wake-ups in series — the page load blocks on the api.
- The free Postgres database is deleted 30 days after creation (14-day grace
  period to upgrade before that happens).

## 1. Push this repo to GitHub

Render deploys from a GitHub (or GitLab) repo. This repo's `origin` is
already `github.com/sumedhkumar/ProTrixPlus`. Commit `render.yaml` and this
doc, then push the branch you want Render to track (Render can deploy any
branch, doesn't have to be `main`).

## 2. Create a free Upstash Redis

1. Go to <https://console.upstash.com>, sign up free (GitHub login works),
   no card required.
2. Create a database (any region close to your Render region, e.g. `us-east`).
3. Copy the **`rediss://` "Redis Connect" URL** (the TLS one, not the REST
   URL) — you'll paste this into Render in step 4.

## 3. Deploy the blueprint on Render

1. Go to <https://dashboard.render.com>, sign up free (GitHub login works).
2. **New** -> **Blueprint** -> connect your GitHub account -> pick the
   `ProTrixPlus` repo and the branch you pushed.
3. Render reads `render.yaml` and shows 1 service (`protrixplus-api`) + 1
   database (`protrixplus-db`). Confirm the plan is **Free**.
4. Render will pause on `PROTRIX_REDIS_URL` (marked `sync: false` in the
   blueprint so the secret isn't committed to git) — paste the Upstash
   `rediss://` URL from step 2.
5. Click **Apply** / **Create New Resources**. First build takes a few
   minutes (Docker build + Postgres provisioning).

## 4. Verify

```
curl -fsS https://protrixplus-api.onrender.com/health
```

(If Render appended a random suffix to the service name, use that actual
URL instead — check the service page.)

To test the signal -> execution flow, adapt
`infra/scripts/simulate_signal.py` to POST at the deployed api URL with the
`PROTRIX_WEBHOOK_SHARED_SECRET` value Render generated (Environment tab on
`protrixplus-api`), instead of `localhost:8000`.

## 5. The web service

`protrixplus-web` is in the same blueprint, built from `web/Dockerfile`, so it
comes up with everything else. Two things wire it to the api:

- **`PROTRIX_API_URL`** on `protrixplus-web` — the api's URL
  (`https://protrixplus-api.onrender.com`). The browser never calls the api
  directly: every request goes to the Next.js server, which forwards it
  server-side (`web/lib/proxy.ts`, `web/lib/api.ts`) carrying the httpOnly
  session cookie. That is why the api's CORS allowlist is still just
  `localhost:3000` and doesn't need the deployed web origin.
- **`PROTRIX_FRONTEND_BASE_URL`** on `protrixplus-api` — the web URL
  (`https://protrixplus-web.onrender.com`). Only used to build the
  password-reset link in mock-sent emails; not load-bearing for anything else.

If Render appended a suffix to either service name, fix both values to the real
URLs in the Environment tab — they point at each other.

`PROTRIX_API_URL` is read **at runtime**, not baked into the image. That is
deliberate: `next.config.mjs` used to expose it through Next's `env:` key,
which inlines the value at *build* time, so an image built once would keep
calling the builder's api URL and silently ignore the variable set on the
service. It is server-only config and the only client imports of `lib/api` are
`import type` (erased at compile time), so the standalone server just reads
`process.env` instead. Verify with:

```
curl -fsS -o /dev/null -w '%{http_code}\n' https://protrixplus-web.onrender.com/login
```

`/login` is the health-check path because `/` redirects and `/login` renders
without a session.

## Tearing it down

Render dashboard -> each service/database -> Settings -> Delete. Or just let
the free Postgres expire after 30 days, which naturally kills the stack.
