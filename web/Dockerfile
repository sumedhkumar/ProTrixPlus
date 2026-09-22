# syntax=docker/dockerfile:1
FROM node:22.12.0-bookworm-slim AS deps
WORKDIR /app
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund

FROM node:22.12.0-bookworm-slim AS build
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
# No PROTRIX_API_URL / PROTRIX_GOOGLE_OAUTH_CLIENT_ID build args: neither is
# inlined at build time (next.config.mjs doesn't declare them under `env:`,
# and app/login|trial/page.tsx read the latter server-side, passing it down
# as a prop rather than a "use client" component reading NEXT_PUBLIC_* from
# process.env directly). Both are read from the environment at *runtime* by
# the standalone server instead - one image works regardless of what the
# builder happened to have set. A build ARG was tried here for the Google
# client ID and silently failed in production: Render does not forward this
# service's dashboard env vars as Docker build args, so it built in empty
# and got dead-code-eliminated by the minifier. Set both on the service
# (Render) or in `environment:` (infra/docker-compose.yml) instead.
COPY --from=deps /app/node_modules ./node_modules
COPY web ./
COPY contracts/typescript /contracts/typescript
RUN npm run build

FROM node:22.12.0-bookworm-slim AS run
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=3000
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
COPY --from=build /app/public ./public
EXPOSE 3000
HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=6 \
    CMD node -e "fetch('http://localhost:3000/login').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"
CMD ["node", "server.js"]
