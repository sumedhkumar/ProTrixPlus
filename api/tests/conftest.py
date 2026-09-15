"""Shared api test fixtures.

Tests split in two:

* pure unit tests (schema validation, auth guard) run everywhere and stub the DB
  dependency;
* ``@pytest.mark.dbtest`` tests need a real PostgreSQL. They are skipped
  automatically when ``PROTRIX_DATABASE_URL`` is unreachable, and always run in
  CI (which provides a postgres service).
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from protrix_contracts.db import metadata
from protrix_contracts.db.session import build_engine
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.identity import MockIdentityProvider
from app.main import create_app
from app.security import get_identity_provider

TEST_SECRET = "unit-test-secret"
TEST_ISSUER = "protrixplus-dev-identity"

_AUDIT_GUARD = """
CREATE OR REPLACE FUNCTION audit_events_block_mutation() RETURNS trigger AS $$
BEGIN RAISE EXCEPTION 'audit_events is insert-only (attempted %)', TG_OP; END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS audit_events_no_update_delete ON audit_events;
CREATE TRIGGER audit_events_no_update_delete
    BEFORE UPDATE OR DELETE ON audit_events
    FOR EACH ROW EXECUTE FUNCTION audit_events_block_mutation();
"""


def _database_url() -> str:
    return os.environ.get(
        "PROTRIX_DATABASE_URL",
        "postgresql+psycopg://protrix:protrix@localhost:5432/protrix",
    )


def _db_available(url: str) -> bool:
    try:
        eng = build_engine(url)
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
        eng.dispose()
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def db_engine():
    url = _database_url()
    if not _db_available(url):
        pytest.skip(f"no PostgreSQL reachable at {url}")
    engine = build_engine(url)
    metadata.drop_all(engine)
    metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text(_AUDIT_GUARD))
    yield engine
    engine.dispose()


@pytest.fixture
def db(db_engine) -> Iterator[Session]:
    connection = db_engine.connect()
    txn = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        txn.rollback()
        connection.close()


@pytest.fixture(autouse=True)
def _test_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROTRIX_DEV_JWT_SECRET", TEST_SECRET)
    monkeypatch.setenv("PROTRIX_DEV_IDENTITY_ENABLED", "true")
    monkeypatch.setenv("PROTRIX_APP_ENV", "ci")
    monkeypatch.setenv("PROTRIX_WEBHOOK_SHARED_SECRET", "dev-webhook-token-change-me")
    # Direct TradingView delivery authenticates with its path token rather than
    # the simulator's request header. Keep both test routes independently
    # configured so an authorized malformed body reaches schema validation.
    monkeypatch.setenv("PROTRIX_TRADINGVIEW_WEBHOOK_SECRET", "dev-webhook-token-change-me")
    get_settings.cache_clear()
    get_identity_provider.cache_clear()
    yield
    get_settings.cache_clear()
    get_identity_provider.cache_clear()


@pytest.fixture
def identity() -> MockIdentityProvider:
    return MockIdentityProvider(secret=TEST_SECRET, issuer=TEST_ISSUER, ttl_seconds=3600)


@pytest.fixture
def client_no_db(identity: MockIdentityProvider) -> Iterator[TestClient]:
    """App with the DB dependency stubbed out (a MagicMock session)."""

    def _fake_db() -> Iterator[MagicMock]:
        yield MagicMock(name="session")

    app = create_app()
    app.dependency_overrides[get_identity_provider] = lambda: identity
    app.dependency_overrides[get_db] = _fake_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def settings() -> Settings:
    return get_settings()
