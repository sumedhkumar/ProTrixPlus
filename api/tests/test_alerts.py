"""Alert catalog (Feature 1: capture + changelog) and bundling into a
strategy (Feature 2). Every field change must be diffed and recorded as an
AuditEvent - this is the real changelog the admin panel reads.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from protrix_contracts.db.models import User, UserRole

pytestmark = pytest.mark.dbtest


@pytest.fixture
def admin_token(db, identity):
    admin = User(email="admin3@example.test", display_name="Admin", role=UserRole.SUPER_ADMIN.value)
    db.add(admin)
    db.commit()
    db.refresh(admin)
    return identity.issue(
        subject=str(admin.id), role=UserRole.SUPER_ADMIN, display_name="Admin", email=admin.email
    )


@pytest.fixture
def client_token(identity, db):
    user = User(email="alert-client@example.test", display_name="Client", role=UserRole.USER.value)
    db.add(user)
    db.commit()
    db.refresh(user)
    return identity.issue(
        subject=str(user.id), role=UserRole.USER, display_name="Client", email=user.email
    )


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_non_admin_cannot_create_alert(client: TestClient, client_token: str) -> None:
    r = client.post(
        "/api/v1/admin/alerts",
        json={"name": "x", "symbol": "EURUSD", "lot_size": "1.00", "timeframe": "5m"},
        headers=_auth(client_token),
    )
    assert r.status_code == 403


def test_create_alert_writes_a_created_changelog_entry(
    client: TestClient, admin_token: str
) -> None:
    r = client.post(
        "/api/v1/admin/alerts",
        json={
            "name": "EURUSD Scalper Entry",
            "symbol": "EURUSD",
            "lot_size": "1.00",
            "timeframe": "5m",
        },
        headers=_auth(admin_token),
    )
    assert r.status_code == 201
    alert = r.json()
    assert alert["strategy_id"] is None

    changelog = client.get(
        f"/api/v1/admin/alerts/{alert['id']}/changelog", headers=_auth(admin_token)
    ).json()
    assert len(changelog) == 1
    assert changelog[0]["event_type"] == "alert.created"


def test_update_alert_diffs_each_changed_field(client: TestClient, admin_token: str) -> None:
    alert = client.post(
        "/api/v1/admin/alerts",
        json={"name": "XAUUSD Trend", "symbol": "XAUUSD", "lot_size": "0.50", "timeframe": "1h"},
        headers=_auth(admin_token),
    ).json()

    updated = client.patch(
        f"/api/v1/admin/alerts/{alert['id']}",
        json={"timeframe": "4h", "lot_size": "0.75"},
        headers=_auth(admin_token),
    )
    assert updated.status_code == 200
    assert updated.json()["timeframe"] == "4h"
    assert updated.json()["lot_size"] == "0.75"

    changelog = client.get(
        f"/api/v1/admin/alerts/{alert['id']}/changelog", headers=_auth(admin_token)
    ).json()
    field_changes = [c for c in changelog if c["event_type"] == "alert.field_changed"]
    assert len(field_changes) == 2
    changed_fields = {c["data"]["field"] for c in field_changes}
    assert changed_fields == {"timeframe", "lot_size"}
    timeframe_change = next(c for c in field_changes if c["data"]["field"] == "timeframe")
    assert timeframe_change["data"]["old_value"] == "1h"
    assert timeframe_change["data"]["new_value"] == "4h"


def test_updating_with_unchanged_value_writes_no_changelog_entry(
    client: TestClient, admin_token: str
) -> None:
    alert = client.post(
        "/api/v1/admin/alerts",
        json={
            "name": "GBPUSD Momentum",
            "symbol": "GBPUSD",
            "lot_size": "1.00",
            "timeframe": "15m",
        },
        headers=_auth(admin_token),
    ).json()

    client.patch(
        f"/api/v1/admin/alerts/{alert['id']}",
        json={"symbol": "GBPUSD"},  # same value
        headers=_auth(admin_token),
    )

    changelog = client.get(
        f"/api/v1/admin/alerts/{alert['id']}/changelog", headers=_auth(admin_token)
    ).json()
    assert all(c["event_type"] != "alert.field_changed" for c in changelog)


def test_bundle_alerts_into_a_strategy(client: TestClient, admin_token: str) -> None:
    strategy = client.post(
        "/api/v1/admin/strategies",
        json={"strategy_key": "bundle-test", "strategy_version": "1.0", "name": "Bundle Test"},
        headers=_auth(admin_token),
    ).json()
    a1 = client.post(
        "/api/v1/admin/alerts",
        json={"name": "A1", "symbol": "EURUSD", "lot_size": "1.00", "timeframe": "5m"},
        headers=_auth(admin_token),
    ).json()
    a2 = client.post(
        "/api/v1/admin/alerts",
        json={"name": "A2", "symbol": "EURUSD", "lot_size": "1.00", "timeframe": "15m"},
        headers=_auth(admin_token),
    ).json()

    r = client.patch(
        f"/api/v1/admin/strategies/{strategy['id']}/alerts",
        json={"alert_ids": [a1["id"], a2["id"]]},
        headers=_auth(admin_token),
    )
    assert r.status_code == 200
    bundled = r.json()
    assert {a["id"] for a in bundled} == {a1["id"], a2["id"]}
    assert all(a["strategy_id"] == strategy["id"] for a in bundled)

    listed = client.get("/api/v1/admin/alerts", headers=_auth(admin_token)).json()
    listed_ids = {a["id"]: a["strategy_id"] for a in listed}
    assert listed_ids[a1["id"]] == strategy["id"]
    assert listed_ids[a2["id"]] == strategy["id"]


def test_bundle_unknown_alert_id_is_404(client: TestClient, admin_token: str) -> None:
    strategy = client.post(
        "/api/v1/admin/strategies",
        json={"strategy_key": "bundle-404", "strategy_version": "1.0", "name": "Bundle 404"},
        headers=_auth(admin_token),
    ).json()

    r = client.patch(
        f"/api/v1/admin/strategies/{strategy['id']}/alerts",
        json={"alert_ids": ["00000000-0000-0000-0000-000000000000"]},
        headers=_auth(admin_token),
    )
    assert r.status_code == 404
