# syntax=docker/dockerfile:1
FROM python:3.12.8-slim-bookworm AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY contracts/python /opt/contracts
RUN python -m pip install --no-cache-dir /opt/contracts

COPY worker/requirements.txt /app/requirements.txt
RUN sed -i '/^protrix-contracts==/d' /app/requirements.txt \
 && python -m pip install --no-cache-dir -r /app/requirements.txt

COPY worker /app

RUN useradd --uid 10001 --no-create-home appuser \
 && chmod +x /app/scripts/entrypoint.sh
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=6 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health').status==200 else 1)"

ENTRYPOINT ["/app/scripts/entrypoint.sh"]
CMD ["python", "-m", "app.main"]
