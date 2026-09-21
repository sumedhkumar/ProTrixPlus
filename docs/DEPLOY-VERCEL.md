# Free, temporary deploy: web on Vercel

Deploys `web` (Next.js) to Vercel's free Hobby plan. Do
[docs/DEPLOY-RENDER.md](DEPLOY-RENDER.md) first — you need the deployed
api's URL for step 3 below.

Vercel can't run the api or worker (they're a persistent server + a
background thread, not short-lived serverless functions) — those stay on
Render. `web` only ever calls the api from server-side code (`lib/api.ts`,
`lib/proxy.ts`, route handlers under `app/api/`), never directly from the
browser, so this split doesn't need any CORS configuration.

## 1. Import the repo on Vercel

1. Go to <https://vercel.com>, sign up free (GitHub login works), no card
   required.
2. **Add New** -> **Project** -> import `sumedhkumar/ProTrixPlus` -> pick the
   branch you're deploying.
3. This repo is a monorepo (api/web/worker all at the root) — set **Root
   Directory** to `web` in the import screen (or Project Settings ->
   General -> Root Directory, if you've already imported). Vercel
   auto-detects the Next.js framework preset from there; no `vercel.json`
   needed.

## 2. Environment variables

Project Settings -> Environment Variables, add for **Production** (and
Preview, if you want branch previews to work too):

| Key | Value |
| --- | --- |
| `PROTRIX_API_URL` | your Render api URL, e.g. `https://protrixplus-api.onrender.com` |
| `PROTRIX_WEBHOOK_SHARED_SECRET` | the value Render generated — copy it from `protrixplus-api`'s Environment tab on Render |

Unlike Render, Vercel makes project env vars available at build time
automatically, which is what `PROTRIX_API_URL` needs (it's inlined into the
Next.js build via `next.config.mjs`'s `env` block) — no extra step.

## 3. Deploy

Click **Deploy**. First build takes a couple of minutes. Vercel gives you a
URL like `https://protrixplus-<hash>.vercel.app` (or `https://protrixplus.vercel.app`
if that exact name was free).

## 4. Verify

Open your Vercel URL's `/login` page, sign in as **USER** or **SUPER_ADMIN**
(mock identity, no password — same as local dev). Watch for a cold-start
delay on the first request if the Render api has spun down from idleness.

## 5. Point the api back at this URL

Back on Render, update `PROTRIX_FRONTEND_BASE_URL` on `protrixplus-api` to
your actual Vercel URL (see [docs/DEPLOY-RENDER.md](DEPLOY-RENDER.md) step 5)
if it differs from the `render.yaml` default.

## Tearing it down

Vercel dashboard -> project -> Settings -> scroll to the bottom -> Delete
Project. Free Hobby projects don't expire on their own, unlike Render's free
Postgres — delete it when you're done with the demo.
