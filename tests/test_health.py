"""Acceptance 1: all services expose a green /health."""

from __future__ import annotations

import httpx
import pytest

from conftest import API_URL, WEB_URL, WORKER_HEALTH_URL, wait_for_health

pytestmark = pytest.mark.integration


def test_api_health_green() -> None:
    body = wait_for_health(API_URL)
    assert body["status"] == "ok"
    assert body["checks"]["postgres"]["status"] == "ok"
    assert body["checks"]["redis"]["status"] == "ok"


def test_worker_health_green() -> None:
    body = wait_for_health(WORKER_HEALTH_URL)
    assert body["service"] == "worker"
    assert body["status"] == "ok"


def test_web_is_up() -> None:
    # `next dev` compiles a route lazily on first hit, so give it room.
    last: Exception | int | None = None
    for _ in range(6):
        try:
            r = httpx.get(f"{WEB_URL}/login", timeout=20)
            if r.status_code == 200:
                return
            last = r.status_code
        except httpx.HTTPError as exc:  # noqa: PERF203
            last = exc
    raise AssertionError(f"web /login not 200 (last={last})")
