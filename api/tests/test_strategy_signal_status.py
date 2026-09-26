"""GET /api/v1/admin/strategies - each row's signal_status ("connected" /
"disconnected") tells the admin whether TradingView is still actively
firing this strategy's alert. We can't detect a deleted TradingView alert
directly (no alert-management API - see app/routers/webhook.py), so this is
inferred purely from how recently a real Signal row arrived, per
marketplace.SIGNAL_IDLE_THRESHOLD."""

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
        email="signal-status-admin@example.test",
        display_name="Admin",
        role=UserRole.SUPER_ADMIN.value,
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    return identity.issue(
        subject=str(admin.id), role=UserRole.SUPER_ADMIN, display_name="Admin", email=admin.email
    )


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_strategy(client: TestClient, admin_token: str, key: str) -> dict:
    return client.post(
        "/api/v1/admin/strategies",
        json={"strategy_key": key, "strategy_version": "1.0", "name": key},
        headers=_auth(admin_token),
    ).json()


def _insert_signal(db, *, strategy_key: str, strategy_version: str, accepted_at: datetime) -> None:
    db.add(
        Signal(
            signal_id=f"sig-{uuid.uuid4()}",
            idempotency_key=f"idem-{uuid.uuid4()}",
            payload_hash="hash",
            schema_version="1.0",
            strategy_key=strategy_key,
            strategy_version=strategy_version,
            action="ENTRY_LONG",
            symbol="XAUUSD",
            timeframe="15m",
            raw_payload={},
            event_time_utc=accepted_at,
            accepted_at=accepted_at,
        )
    )
    db.commit()


def test_strategy_with_no_signal_ever_is_disconnected(client: TestClient, admin_token: str) -> None:
    _create_strategy(client, admin_token, "sig-status-never")
    catalog = client.get("/api/v1/admin/strategies", headers=_auth(admin_token)).json()
    row = next(s for s in catalog if s["strategy_key"] == "sig-status-never")
    assert row["signal_status"] == "disconnected"
    assert row["last_signal_at"] is None


def test_strategy_with_a_recent_signal_is_connected(
    client: TestClient, db, admin_token: str
) -> None:
    _create_strategy(client, admin_token, "sig-status-recent")
    _insert_signal(
        db,
        strategy_key="sig-status-recent",
        strategy_version="1.0",
        accepted_at=datetime.now(UTC) - timedelta(minutes=5),
    )
    catalog = client.get("/api/v1/admin/strategies", headers=_auth(admin_token)).json()
    row = next(s for s in catalog if s["strategy_key"] == "sig-status-recent")
    assert row["signal_status"] == "connected"
    assert row["last_signal_at"] is not None


def test_strategy_with_a_stale_signal_is_disconnected(
    client: TestClient, db, admin_token: str
) -> None:
    _create_strategy(client, admin_token, "sig-status-stale")
    _insert_signal(
        db,
        strategy_key="sig-status-stale",
        strategy_version="1.0",
        accepted_at=datetime.now(UTC) - timedelta(hours=48),
    )
    catalog = client.get("/api/v1/admin/strategies", headers=_auth(admin_token)).json()
    row = next(s for s in catalog if s["strategy_key"] == "sig-status-stale")
    assert row["signal_status"] == "disconnected"
    assert row["last_signal_at"] is not None
