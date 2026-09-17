# syntax=docker/dockerfile:1
FROM node:22.12.0-bookworm-slim AS deps
WORKDIR /app
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund

FROM node:22.12.0-bookworm-slim AS build
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
# Next.js reads this during the image build because next.config.mjs exposes
# the server-only API URL through its env configuration.
ARG PROTRIX_API_URL=http://api:8000
ENV PROTRIX_API_URL=${PROTRIX_API_URL}
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
