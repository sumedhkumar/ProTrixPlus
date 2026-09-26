"""GET /api/v1/admin/strategies/unmapped-signals - real (strategy_key,
strategy_version) pairs TradingView is already sending that don't match any
row in the strategies table yet. Powers the admin Create Strategy dropdown
so the admin picks from what's actually arriving instead of hand-typing a
key that has to match a live signal byte-for-byte."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from protrix_contracts.db.models import Signal, User, UserRole

pytestmark = pytest.mark.dbtest


@pytest.fixture
def admin_token(db, identity):
    admin = User(
        email="unmapped-admin@example.test", display_name="Admin", role=UserRole.SUPER_ADMIN.value
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    return identity.issue(
        subject=str(admin.id), role=UserRole.SUPER_ADMIN, display_name="Admin", email=admin.email
    )


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _insert_signal(
    db, *, strategy_key: str, strategy_version: str, symbol: str, timeframe: str, accepted_at
) -> None:
    db.add(
        Signal(
            signal_id=f"sig-{uuid.uuid4()}",
            idempotency_key=f"idem-{uuid.uuid4()}",
            payload_hash="hash",
            schema_version="1.0",
            strategy_key=strategy_key,
            strategy_version=strategy_version,
            action="ENTRY_LONG",
            symbol=symbol,
            timeframe=timeframe,
            raw_payload={},
            event_time_utc=accepted_at,
            accepted_at=accepted_at,
        )
    )
    db.commit()


def test_signal_with_no_matching_strategy_is_unmapped(
    client: TestClient, db, admin_token: str
) -> None:
    _insert_signal(
        db,
        strategy_key="brand-new-strategy",
        strategy_version="1.0",
        symbol="XAUUSD",
        timeframe="15m",
        accepted_at=datetime.now(UTC),
    )
    r = client.get("/api/v1/admin/strategies/unmapped-signals", headers=_auth(admin_token))
    assert r.status_code == 200
    row = next(x for x in r.json() if x["strategy_key"] == "brand-new-strategy")
    assert row["strategy_version"] == "1.0"
    assert row["symbol"] == "XAUUSD"
    assert row["timeframe"] == "15m"
    assert row["signal_count"] == 1


def test_signal_matching_an_existing_strategy_is_not_unmapped(
    client: TestClient, db, admin_token: str
) -> None:
    strategy = client.post(
        "/api/v1/admin/strategies",
        json={
            "strategy_key": "already-mapped",
            "strategy_version": "1.0",
            "name": "Already Mapped",
        },
        headers=_auth(admin_token),
    ).json()
    assert strategy["strategy_key"] == "already-mapped"

    _insert_signal(
        db,
        strategy_key="already-mapped",
        strategy_version="1.0",
        symbol="EURUSD",
        timeframe="1h",
        accepted_at=datetime.now(UTC),
    )
    r = client.get("/api/v1/admin/strategies/unmapped-signals", headers=_auth(admin_token))
    assert r.status_code == 200
    assert "already-mapped" not in [x["strategy_key"] for x in r.json()]


def test_multiple_signals_for_the_same_unmapped_key_are_counted_and_use_latest_symbol(
    client: TestClient, db, admin_token: str
) -> None:
    now = datetime.now(UTC)
    _insert_signal(
        db,
        strategy_key="multi-fire",
        strategy_version="1.0",
        symbol="OLDPAIR",
        timeframe="5m",
        accepted_at=now - timedelta(hours=1),
    )
    _insert_signal(
        db,
        strategy_key="multi-fire",
        strategy_version="1.0",
        symbol="NEWPAIR",
        timeframe="5m",
        accepted_at=now,
    )
    r = client.get("/api/v1/admin/strategies/unmapped-signals", headers=_auth(admin_token))
    row = next(x for x in r.json() if x["strategy_key"] == "multi-fire")
    assert row["signal_count"] == 2
    assert row["symbol"] == "NEWPAIR"  # most recent signal wins


def test_non_admin_cannot_list_unmapped_signals(client: TestClient, identity, db) -> None:
    user = User(email="unmapped-user@example.test", display_name="User", role=UserRole.USER.value)
    db.add(user)
    db.commit()
    db.refresh(user)
    token = identity.issue(
        subject=str(user.id), role=UserRole.USER, display_name="User", email=user.email
    )
    r = client.get("/api/v1/admin/strategies/unmapped-signals", headers=_auth(token))
    assert r.status_code == 403
