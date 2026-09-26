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
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest
from fastapi.testclient import TestClient
from protrix_contracts.db import metadata
from protrix_contracts.db.session import build_engine
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.email import MockEmailSender, get_email_sender
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


# infra/docker-compose.yml maps the local dev/demo stack's postgres to this
# fixed host port (infra/.env PROTRIX_POSTGRES_PORT) - see infra/README.md.
# A real incident: running this suite with PROTRIX_DATABASE_URL pointed at
# that port ran drop_all() against it and destroyed every real account,
# strategy, and execution twice. This fixture must never be able to do that
# again without an explicit, conscious override.
_DEV_STACK_PORT = "55432"


def _guard_against_dev_database(url: str) -> None:
    port = str(make_url(url).port)
    if port == _DEV_STACK_PORT and not os.environ.get("PROTRIX_ALLOW_TEST_DB_WIPE"):
        pytest.exit(
            f"\n[conftest] Refusing to run db tests against {url}\n"
            f"Port {_DEV_STACK_PORT} is the local ProTrixPlus dev/demo stack "
            "(infra/.env PROTRIX_POSTGRES_PORT) - this fixture drops every "
            "table. Point PROTRIX_DATABASE_URL at a disposable database "
            "instead, or set PROTRIX_ALLOW_TEST_DB_WIPE=1 if you are certain "
            f"port {_DEV_STACK_PORT} is disposable this time.",
            returncode=1,
        )


@pytest.fixture(scope="session")
def db_engine():
    url = _database_url()
    if not _db_available(url):
        pytest.skip(f"no PostgreSQL reachable at {url}")
    _guard_against_dev_database(url)
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


# A real incident: a test asserting the "MetaApi not configured" 503 path
# never mocked anything, trusting the ambient env to have no
# PROTRIX_METAAPI_TOKEN set. When a real token loaded instead (from
# ../infra/.env, config.py's env_file fallback to the live deployment's own
# credential), that test's request ran for real against MetaApi's live
# provisioning API and created a real, billed, orphaned account - twice, on
# two separate runs. Every real success-path test already mocks at the
# metaapi_client function level (never touching httpx), so blocking outbound
# calls to MetaApi's real hosts here costs nothing and closes this off for
# good, regardless of what any test does or doesn't set.
_METAAPI_HOST_FRAGMENT = "agiliumtrade"


def _blocked_metaapi_call(method: str, url: str, *args: Any, **kwargs: Any) -> None:
    raise RuntimeError(
        f"Test attempted a REAL network call ({method} {url}) to MetaApi. "
        "Tests must mock app.services.metaapi_client functions, never let a "
        "real call through - see the incident note above this fixture."
    )


def _extract_url(name: str, args: tuple[Any, ...], kwargs: dict[str, Any]) -> str:
    # httpx.request(method, url, ...) - url is the 2nd positional arg;
    # httpx.get/post/put/delete(url, ...) - url is the 1st.
    url_index = 1 if name == "request" else 0
    if len(args) > url_index:
        return str(args[url_index])
    return str(kwargs.get("url", ""))


@pytest.fixture(autouse=True)
def _block_real_metaapi_network(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("request", "get", "post", "put", "delete"):
        real_fn = getattr(httpx, name)

        def _guarded(
            *args: Any, _real_fn: Any = real_fn, _name: str = name, **kwargs: Any
        ) -> httpx.Response:
            if _METAAPI_HOST_FRAGMENT in _extract_url(_name, args, kwargs):
                _blocked_metaapi_call(_name.upper(), _extract_url(_name, args, kwargs))
            return _real_fn(*args, **kwargs)  # type: ignore[no-any-return]

        monkeypatch.setattr(httpx, name, _guarded)


@pytest.fixture(autouse=True)
def _test_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROTRIX_DEV_JWT_SECRET", TEST_SECRET)
    monkeypatch.setenv("PROTRIX_DEV_IDENTITY_ENABLED", "true")
    monkeypatch.setenv("PROTRIX_APP_ENV", "ci")
    monkeypatch.setenv("PROTRIX_WEBHOOK_SHARED_SECRET", "dev-webhook-token-change-me")
    monkeypatch.setenv("PROTRIX_TRADINGVIEW_WEBHOOK_SECRET", "dev-webhook-token-change-me")
    get_settings.cache_clear()
    get_identity_provider.cache_clear()
    get_email_sender.cache_clear()
    yield
    get_settings.cache_clear()
    get_identity_provider.cache_clear()
    get_email_sender.cache_clear()


@pytest.fixture
def identity() -> MockIdentityProvider:
    return MockIdentityProvider(secret=TEST_SECRET, issuer=TEST_ISSUER, ttl_seconds=3600)


@pytest.fixture
def mock_email() -> MockEmailSender:
    return MockEmailSender()


@pytest.fixture
def client_no_db(
    identity: MockIdentityProvider, mock_email: MockEmailSender
) -> Iterator[TestClient]:
    """App with the DB dependency stubbed out (a MagicMock session)."""

    def _fake_db() -> Iterator[MagicMock]:
        yield MagicMock(name="session")

    app = create_app()
    app.dependency_overrides[get_identity_provider] = lambda: identity
    app.dependency_overrides[get_email_sender] = lambda: mock_email
    app.dependency_overrides[get_db] = _fake_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def settings() -> Settings:
    return get_settings()


@pytest.fixture
def client(
    db: Session, identity: MockIdentityProvider, mock_email: MockEmailSender
) -> Iterator[TestClient]:
    """App wired to a real (transactional, rolled-back) PostgreSQL session.

    For routes that actually read/write - auth signup/login, ingest via HTTP,
    etc. - as opposed to ``client_no_db``'s stubbed session.
    """
    app = create_app()
    app.dependency_overrides[get_identity_provider] = lambda: identity
    app.dependency_overrides[get_email_sender] = lambda: mock_email
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
