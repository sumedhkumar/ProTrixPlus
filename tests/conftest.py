"""Fixtures for the integration suite.

All tests here need the composed stack (``docker compose -f
infra/docker-compose.yml up``). They auto-skip when the api is unreachable, so a
plain ``pytest tests/`` on a laptop with nothing running is green-by-skip; CI
brings the stack up first.
"""

from __future__ import annotations

import os
import time

import httpx
import pytest
from sqlalchemy import create_engine, text

API_URL = os.environ.get("PROTRIX_API_URL", "http://127.0.0.1:8000")
WORKER_HEALTH_URL = os.environ.get("PROTRIX_WORKER_HEALTH_URL", "http://127.0.0.1:8100")
WEB_URL = os.environ.get("PROTRIX_WEB_URL", "http://127.0.0.1:3000")
DATABASE_URL = os.environ.get(
    "PROTRIX_DATABASE_URL", "postgresql+psycopg://protrix:protrix@127.0.0.1:5432/protrix"
).replace("postgresql+psycopg://", "postgresql+psycopg://")
REDIS_URL = os.environ.get("PROTRIX_REDIS_URL", "redis://127.0.0.1:6379/0")
WEBHOOK_TOKEN = os.environ.get("PROTRIX_WEBHOOK_SHARED_SECRET", "dev-webhook-token-change-me")
COMPOSE_FILE = os.environ.get("PROTRIX_COMPOSE_FILE", "infra/docker-compose.yml")


def _stack_up() -> bool:
    try:
        return httpx.get(f"{API_URL}/health", timeout=8).status_code in (200, 503)
    except Exception:
        return False


@pytest.fixture(scope="session", autouse=True)
def _require_stack() -> None:
    if not _stack_up():
        pytest.skip(f"composed stack not reachable at {API_URL}")


def wait_for_health(url: str, *, timeout: float = 60.0) -> dict:
    deadline = time.time() + timeout
    last: dict = {}
    while time.time() < deadline:
        try:
            r = httpx.get(f"{url}/health", timeout=3)
            last = r.json()
            if r.status_code == 200 and last.get("status") == "ok":
                return last
        except Exception:
            pass
        time.sleep(1)
    raise AssertionError(f"{url}/health not green in {timeout}s (last={last})")


@pytest.fixture(scope="session")
def stack_healthy() -> None:
    wait_for_health(API_URL)
    wait_for_health(WORKER_HEALTH_URL)


@pytest.fixture(scope="session")
def engine():
    eng = create_engine(DATABASE_URL, future=True)
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine):
    with engine.connect() as conn:
        yield conn


def count(conn, table: str) -> int:
    return int(conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one())
