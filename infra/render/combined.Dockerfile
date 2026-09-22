# Combined api + worker image, used only for the free Render deploy
# (docs/DEPLOY-RENDER.md). Render's free tier has no free Background Worker
# plan, so both processes run in one free Web Service container instead.
# Local dev keeps using the real api/Dockerfile + worker/Dockerfile via
# infra/docker-compose.yml - this file changes nothing about that setup.
#
# Build context is the repo root (same as api/Dockerfile and worker/Dockerfile).
FROM python:3.12.8-slim-bookworm AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# 1) Shared contract package.
COPY contracts/python /opt/contracts
RUN python -m pip install --no-cache-dir /opt/contracts

# 2) api's requirements.txt is a strict superset of worker's (same pins) -
#    one install covers both processes.
COPY api/requirements.txt /app/requirements.txt
RUN sed -i '/^protrix-contracts==/d' /app/requirements.txt \
 && python -m pip install --no-cache-dir -r /app/requirements.txt

# 3) Both services' source, kept in separate directories (both use the
#    top-level package name `app`, so they can't share one directory).
COPY api /app/api
COPY worker /app/worker
COPY infra/render/combined-entrypoint.sh /app/combined-entrypoint.sh

RUN useradd --uid 10001 --no-create-home appuser \
 && chmod +x /app/combined-entrypoint.sh /app/api/scripts/entrypoint.sh /app/worker/scripts/entrypoint.sh
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=6 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health').status==200 else 1)"

ENTRYPOINT ["/app/combined-entrypoint.sh"]
