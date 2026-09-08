"""Unit: /health always answers with the documented shape."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app


def test_health_shape() -> None:
    with TestClient(create_app()) as c:
        r = c.get("/health")
    assert r.status_code in (200, 503)
    body = r.json()
    assert body["service"] == "api"
    assert set(body["checks"]) == {"postgres", "redis"}
    assert body["status"] in {"ok", "degraded"}
