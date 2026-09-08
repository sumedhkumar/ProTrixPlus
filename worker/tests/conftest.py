"""Worker test fixtures.

``@pytest.mark.dbtest`` needs PostgreSQL + Redis; auto-skipped when either is
unreachable, always run in CI.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from protrix_contracts.db import metadata
from protrix_contracts.db.models import Signal, Strategy, StrategyAssignment, User
from protrix_contracts.db.session import build_engine, build_session_factory
from redis import Redis
from sqlalchemy import text
from sqlalchemy.orm import Session

DB_URL = os.environ.get(
    "PROTRIX_DATABASE_URL", "postgresql+psycopg://protrix:protrix@localhost:5432/protrix"
)
REDIS_URL = os.environ.get("PROTRIX_REDIS_URL", "redis://localhost:6379/0")

_AUDIT_GUARD = """
CREATE OR REPLACE FUNCTION audit_events_block_mutation() RETURNS trigger AS $$
BEGIN RAISE EXCEPTION 'audit_events is insert-only (attempted %)', TG_OP; END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS audit_events_no_update_delete ON audit_events;
CREATE TRIGGER audit_events_no_update_delete
    BEFORE UPDATE OR DELETE ON audit_events
    FOR EACH ROW EXECUTE FUNCTION audit_events_block_mutation();
"""

STRATEGY_KEY = "trend-rider"
STRATEGY_VERSION = "2025.09"


def _reachable() -> bool:
    try:
        eng = build_engine(DB_URL)
        with eng.connect() as c:
            c.execute(text("SELECT 1"))
        eng.dispose()
        Redis.from_url(REDIS_URL, socket_connect_timeout=2).ping()
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def _services() -> None:
    if not _reachable():
        pytest.skip(f"need PostgreSQL ({DB_URL}) and Redis ({REDIS_URL})")


@pytest.fixture(scope="session")
def engine(_services: None):
    eng = build_engine(DB_URL)
    metadata.drop_all(eng)
    metadata.create_all(eng)
    with eng.begin() as conn:
        conn.execute(text(_AUDIT_GUARD))
    yield eng
    eng.dispose()


@pytest.fixture
def sf(engine):
    return build_session_factory(engine)


@pytest.fixture
def clean_db(engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE executions, order_intents, outbox, signals, "
                "strategy_assignments, strategies, users, audit_events, "
                "mock_broker_deals RESTART IDENTITY CASCADE"
            )
        )


@pytest.fixture
def redis_client(_services: None) -> Iterator[Redis]:
    client = Redis.from_url(REDIS_URL, decode_responses=True)
    client.flushdb()
    yield client
    client.flushdb()
    client.close()


@pytest.fixture
def seeded(sf, clean_db) -> dict[str, uuid.UUID]:
    ids: dict[str, uuid.UUID] = {}
    with sf() as s:
        strat = Strategy(
            strategy_key=STRATEGY_KEY,
            strategy_version=STRATEGY_VERSION,
            name="Trend Rider",
            is_active=True,
        )
        s.add(strat)
        s.flush()
        ids["strategy"] = strat.id
        for slug in ("alice", "bob"):
            u = User(email=f"{slug}@example.test", display_name=slug.title(), role="USER")
            s.add(u)
            s.flush()
            ids[slug] = u.id
            s.add(
                StrategyAssignment(
                    user_id=u.id,
                    strategy_id=strat.id,
                    master_lot=Decimal("1.00"),
                    multiplier=Decimal("1.0000"),
                    multiplier_min=Decimal("0.5000"),
                    multiplier_max=Decimal("2.0000"),
                    status="ACTIVE",
                )
            )
        s.commit()
    return ids


def make_signal(sf, *, signal_id: str = "sig-w-1", action: str = "BUY") -> uuid.UUID:
    with sf() as s:
        sig = Signal(
            signal_id=signal_id,
            idempotency_key=f"{STRATEGY_KEY}:{STRATEGY_VERSION}:{signal_id}",
            payload_hash=f"sha256:test-{signal_id}",
            schema_version="1.0",
            strategy_key=STRATEGY_KEY,
            strategy_version=STRATEGY_VERSION,
            action=action,
            symbol="EURUSD",
            timeframe="15m",
            raw_payload={"signal_id": signal_id},
            event_time_utc=datetime.now(UTC),
            accepted_at=datetime.now(UTC),
        )
        s.add(sig)
        s.commit()
        return sig.id


@pytest.fixture
def db_session(sf) -> Iterator[Session]:
    s = sf()
    try:
        yield s
    finally:
        s.close()
