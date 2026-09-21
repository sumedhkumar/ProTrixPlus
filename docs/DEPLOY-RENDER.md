# Free, temporary deploy on Render

This deploys the S0 stack (web, api, worker, Postgres) to Render's free tier,
plus a free Upstash Redis (Render doesn't offer free Redis). Everything here
uses mock adapters/identity, same as local dev — no real credentials needed.

**Free-tier caveats (fine for a temporary demo, not for anything long-lived):**
- `protrixplus-api` and `protrixplus-web` spin down after ~15 min idle; the
  next request wakes them up (10-50s cold start).
- The free Postgres database is deleted 30 days after creation (14-day grace
  period to upgrade before that happens).
- The free worker doesn't spin down, but shares the same free-tier CPU/RAM
  limits.

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
3. Render reads `render.yaml` and shows 3 services (`protrixplus-api`,
   `protrixplus-worker`, `protrixplus-web`) + 1 database
   (`protrixplus-db`). Confirm plans are all **Free**.
4. Render will pause on `PROTRIX_REDIS_URL` (marked `sync: false` in the
   blueprint so the secret isn't committed to git) — paste the Upstash
   `rediss://` URL from step 2 for **both** `protrixplus-api` and
   `protrixplus-worker`.
5. Click **Apply** / **Create New Resources**. First build takes ~5-10 min
   (Docker builds for 3 services + Postgres provisioning).

## 4. Fix up the cross-service URLs (one-time, after first deploy)

`render.yaml` assumes the default Render URLs
(`https://protrixplus-api.onrender.com`, `https://protrixplus-web.onrender.com`).
If Render appended a random suffix (happens if the name was taken), open each
service's **Environment** tab and update:

- On `protrixplus-web`: `PROTRIX_API_URL` -> the actual api service URL.
- On `protrixplus-api`: `PROTRIX_FRONTEND_BASE_URL` -> the actual web service URL.

`PROTRIX_API_URL` is baked into the Next.js build at build time, so after
changing it, **manually redeploy** `protrixplus-web` (Manual Deploy -> Clear
build cache & deploy) for it to take effect.

## 5. Verify

```
curl -fsS https://protrixplus-api.onrender.com/health
```

Open `https://protrixplus-web.onrender.com/login` in a browser, sign in as
**USER** or **SUPER_ADMIN** (mock identity, no password — same as local dev).

To test the signal -> execution flow, adapt
`infra/scripts/simulate_signal.py` to POST at the deployed api URL with the
`PROTRIX_WEBHOOK_SHARED_SECRET` value Render generated (Environment tab on
`protrixplus-api`), instead of `localhost:8000`.

## Tearing it down

Render dashboard -> each service/database -> Settings -> Delete. Or just let
the free Postgres expire after 30 days, which naturally kills the stack.
