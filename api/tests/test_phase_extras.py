"""Phase 1 (alert-config), Phase 3 (MT5 connection, stubbed), Phase 6
(P&L summary), Phase 10 (ops-summary) - all against a real PostgreSQL."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from protrix_contracts.db.models import User, UserRole

pytestmark = pytest.mark.dbtest


@pytest.fixture
def admin_token(db, identity):
    admin = User(email="admin2@example.test", display_name="Admin", role=UserRole.SUPER_ADMIN.value)
    db.add(admin)
    db.commit()
    db.refresh(admin)
    return identity.issue(
        subject=str(admin.id), role=UserRole.SUPER_ADMIN, display_name="Admin", email=admin.email
    )


@pytest.fixture
def client_user(db):
    user = User(email="pnl-client@example.test", display_name="PnlClient", role=UserRole.USER.value)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def client_token(identity, client_user):
    return identity.issue(
        subject=str(client_user.id),
        role=UserRole.USER,
        display_name="PnlClient",
        email=client_user.email,
    )


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# --------------------------------------------------------------------------
# Phase 1: alert-config
# --------------------------------------------------------------------------


def test_alert_config_never_returns_a_secret(client: TestClient, admin_token: str) -> None:
    strategy = client.post(
        "/api/v1/admin/strategies",
        json={"strategy_key": "supertrend", "strategy_version": "1.0", "name": "Supertrend"},
        headers=_auth(admin_token),
    ).json()

    r = client.get(
        f"/api/v1/admin/strategies/{strategy['id']}/alert-config", headers=_auth(admin_token)
    )
    assert r.status_code == 200
    body = r.json()
    assert body["alert_message_template"]["strategy_key"] == "supertrend"
    assert body["alert_message_template"]["strategy_version"] == "1.0"
    # The actual webhook secret must never appear in this response.
    assert "your-webhook-secret" in body["webhook_path_template"]


# --------------------------------------------------------------------------
# Phase 3: MT5 connection (stub)
# --------------------------------------------------------------------------


def test_mt5_connection_set_then_check_is_honestly_pending(
    client: TestClient, client_token: str
) -> None:
    assert client.get("/api/v1/me/mt5-connection", headers=_auth(client_token)).json() is None

    set_r = client.put(
        "/api/v1/me/mt5-connection",
        json={"broker_server": "ICMarketsSC-Live", "login": "12345678"},
        headers=_auth(client_token),
    )
    assert set_r.status_code == 200
    assert set_r.json()["status"] == "NOT_CONFIGURED"

    check_r = client.post("/api/v1/me/mt5-connection/check", headers=_auth(client_token))
    assert check_r.status_code == 200
    body = check_r.json()
    # Must never fabricate CONNECTED - no real MetaApi credentials exist yet.
    assert body["status"] == "PENDING"
    assert "MetaApi" in body["last_error"]


def test_mt5_connection_check_without_setup_is_404(client: TestClient, client_token: str) -> None:
    r = client.post("/api/v1/me/mt5-connection/check", headers=_auth(client_token))
    assert r.status_code == 404


def test_mt5_connection_disconnect_removes_it(client: TestClient, client_token: str) -> None:
    client.put(
        "/api/v1/me/mt5-connection",
        json={"broker_server": "ICMarketsSC-Live", "login": "999"},
        headers=_auth(client_token),
    )
    del_r = client.delete("/api/v1/me/mt5-connection", headers=_auth(client_token))
    assert del_r.status_code == 204
    assert client.get("/api/v1/me/mt5-connection", headers=_auth(client_token)).json() is None


def test_mt5_connection_disconnect_without_setup_is_404(
    client: TestClient, client_token: str
) -> None:
    r = client.delete("/api/v1/me/mt5-connection", headers=_auth(client_token))
    assert r.status_code == 404


def test_admin_sees_all_client_mt5_connections(
    client: TestClient, admin_token: str, client_token: str
) -> None:
    client.put(
        "/api/v1/me/mt5-connection",
        json={"broker_server": "ICMarketsSC-Live", "login": "999"},
        headers=_auth(client_token),
    )
    r = client.get("/api/v1/admin/mt5-connections", headers=_auth(admin_token))
    assert r.status_code == 200
    assert any(row["login"] == "999" for row in r.json())


# --------------------------------------------------------------------------
# Phase 6: P&L summary
# --------------------------------------------------------------------------


def test_pnl_summary_with_no_executions_is_zero_not_fabricated(
    client: TestClient, client_token: str
) -> None:
    r = client.get("/api/v1/me/pnl-summary", headers=_auth(client_token))
    assert r.status_code == 200
    body = r.json()
    assert body["realized_pnl"] == "0"
    assert body["attributable_trades"] == 0
    assert body["match_rate_percent"] == 0


# --------------------------------------------------------------------------
# Phase 10: ops-summary
# --------------------------------------------------------------------------


def test_ops_summary_reflects_revoked_assignments(
    client: TestClient, admin_token: str, client_user
) -> None:
    strategy = client.post(
        "/api/v1/admin/strategies",
        json={"strategy_key": "ops-test", "strategy_version": "1.0", "name": "Ops"},
        headers=_auth(admin_token),
    ).json()
    assignment = client.post(
        "/api/v1/admin/assignments",
        json={"user_id": str(client_user.id), "strategy_id": strategy["id"], "master_lot": "1.00"},
        headers=_auth(admin_token),
    ).json()

    before = client.get("/api/v1/admin/ops-summary", headers=_auth(admin_token)).json()

    client.patch(
        f"/api/v1/admin/assignments/{assignment['id']}",
        json={"revoke": True},
        headers=_auth(admin_token),
    )

    after = client.get("/api/v1/admin/ops-summary", headers=_auth(admin_token)).json()
    assert after["revoked_assignments"] == before["revoked_assignments"] + 1


def test_non_admin_cannot_reach_ops_summary(client: TestClient, client_token: str) -> None:
    r = client.get("/api/v1/admin/ops-summary", headers=_auth(client_token))
    assert r.status_code == 403
