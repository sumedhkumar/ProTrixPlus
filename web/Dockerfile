# syntax=docker/dockerfile:1
FROM node:22.12.0-bookworm-slim AS deps
WORKDIR /app
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund

FROM node:22.12.0-bookworm-slim AS build
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
# No PROTRIX_API_URL build arg: next.config.mjs no longer inlines it, so the
# api URL is read from the environment at runtime by the standalone server.
# That means one image works against any api host - set PROTRIX_API_URL on the
# service (Render) or in `environment:` (infra/docker-compose.yml).
#
# NEXT_PUBLIC_GOOGLE_CLIENT_ID is different: it's read client-side
# (components/GoogleSignInButton.tsx), and Next.js only inlines
# NEXT_PUBLIC_ vars at *build* time, so it has to be a build ARG here -
# Render passes matching-named service env vars through as build args
# automatically for Docker-runtime services.
ARG NEXT_PUBLIC_GOOGLE_CLIENT_ID
ENV NEXT_PUBLIC_GOOGLE_CLIENT_ID=$NEXT_PUBLIC_GOOGLE_CLIENT_ID
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
