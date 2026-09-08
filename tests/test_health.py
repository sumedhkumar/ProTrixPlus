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
    assert httpx.get(f"{WEB_URL}/login", timeout=5).status_code == 200
