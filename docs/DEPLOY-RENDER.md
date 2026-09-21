# Free, temporary deploy: api + worker + Postgres on Render

This deploys the api and worker (Postgres too) to Render's free tier, plus a
free Upstash Redis (Render doesn't offer free Redis). `web` (Next.js) deploys
separately to Vercel — see [docs/DEPLOY-VERCEL.md](DEPLOY-VERCEL.md). Do this
doc first: Vercel's `web` needs the api's URL as a build-time env var.

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
  the same container).
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

## 5. After web is deployed on Vercel

Update `PROTRIX_FRONTEND_BASE_URL` on `protrixplus-api` (Environment tab) to
your actual Vercel URL if it differs from the `render.yaml` default
(`https://protrixplus.vercel.app`) — used to build the password-reset link in
mock-sent emails, not load-bearing for anything else.

## Tearing it down

Render dashboard -> each service/database -> Settings -> Delete. Or just let
the free Postgres expire after 30 days, which naturally kills the stack.
