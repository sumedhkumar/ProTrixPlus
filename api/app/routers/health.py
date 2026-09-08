"""GET /health - liveness + dependency checks (postgres, redis)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Response, status
from redis import Redis
from sqlalchemy import text

from app import __version__
from app.config import get_settings
from app.db import get_engine

log = logging.getLogger("api.health")
router = APIRouter(tags=["health"])


def _check_postgres() -> dict[str, str]:
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok"}
    except Exception as exc:  # noqa: BLE001 - report, don't crash
        return {"status": "error", "detail": exc.__class__.__name__}


def _check_redis() -> dict[str, str]:
    try:
        client: Redis = Redis.from_url(get_settings().redis_url, socket_connect_timeout=2)
        with client:
            client.ping()
        return {"status": "ok"}
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "detail": exc.__class__.__name__}


@router.get("/health")
def health(response: Response) -> dict[str, object]:
    checks = {"postgres": _check_postgres(), "redis": _check_redis()}
    healthy = all(c["status"] == "ok" for c in checks.values())
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "service": get_settings().service_name,
        "version": __version__,
        "status": "ok" if healthy else "degraded",
        "checks": checks,
    }
