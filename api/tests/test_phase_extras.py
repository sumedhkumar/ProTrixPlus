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
    assert del_r.status_code == 200
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


def test_admin_attaches_metaapi_account_to_a_clients_connection(
    client: TestClient, admin_token: str, client_token: str
) -> None:
    set_r = client.put(
        "/api/v1/me/mt5-connection",
        json={"broker_server": "MetaQuotes-Demo", "login": "112861630"},
        headers=_auth(client_token),
    )
    connection_id = set_r.json()["id"]
    assert set_r.json()["metaapi_account_id"] is None  # never set by the client themselves

    r = client.patch(
        f"/api/v1/admin/mt5-connections/{connection_id}/metaapi",
        json={
            "metaapi_account_id": "b6b65caf-5b94-476e-8e7b-889b819f4f97",
            "metaapi_region": "london",
        },
        headers=_auth(admin_token),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["metaapi_account_id"] == "b6b65caf-5b94-476e-8e7b-889b819f4f97"
    assert body["metaapi_region"] == "london"

    mine = client.get("/api/v1/me/mt5-connection", headers=_auth(client_token)).json()
    assert mine["metaapi_account_id"] == "b6b65caf-5b94-476e-8e7b-889b819f4f97"


def test_admin_attach_metaapi_account_404s_for_unknown_connection(
    client: TestClient, admin_token: str
) -> None:
    r = client.patch(
        "/api/v1/admin/mt5-connections/00000000-0000-0000-0000-000000000000/metaapi",
        json={"metaapi_account_id": "x", "metaapi_region": "london"},
        headers=_auth(admin_token),
    )
    assert r.status_code == 404


def test_non_admin_cannot_attach_metaapi_account(client: TestClient, client_token: str) -> None:
    set_r = client.put(
        "/api/v1/me/mt5-connection",
        json={"broker_server": "MetaQuotes-Demo", "login": "1"},
        headers=_auth(client_token),
    )
    connection_id = set_r.json()["id"]
    r = client.patch(
        f"/api/v1/admin/mt5-connections/{connection_id}/metaapi",
        json={"metaapi_account_id": "x", "metaapi_region": "london"},
        headers=_auth(client_token),
    )
    assert r.status_code == 403


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


def test_ops_summary_counts_duplicate_signal_deliveries(
    client: TestClient, admin_token: str
) -> None:
    payload = {
        "schema_version": "1.0",
        "strategy_key": "ops-dup-test",
        "strategy_version": "1.0",
        "signal_id": "sig-dup-test-1",
        "event_time_utc": "2026-09-08T10:15:00Z",
        "action": "BUY",
        "symbol": "EURUSD",
        "timeframe": "15m",
    }
    headers = {"X-Webhook-Token": "dev-webhook-token-change-me"}

    before = client.get("/api/v1/admin/ops-summary", headers=_auth(admin_token)).json()

    first = client.post("/webhook/tradingview", json=payload, headers=headers)
    assert first.status_code == 202
    assert first.json()["duplicate"] is False

    redelivered = client.post("/webhook/tradingview", json=payload, headers=headers)
    assert redelivered.status_code == 200
    assert redelivered.json()["duplicate"] is True

    after = client.get("/api/v1/admin/ops-summary", headers=_auth(admin_token)).json()
    assert after["duplicate_signal_count"] == before["duplicate_signal_count"] + 1
    # the fresh accept itself is not a duplicate, so total_signals moves by 1, not 2
    assert after["total_signals"] == before["total_signals"] + 1


def test_ops_summary_counts_disconnected_mt5_bridges(
    client: TestClient, admin_token: str, client_user, db
) -> None:
    from protrix_contracts.db.models import Mt5Connection, Mt5ConnectionStatus

    before = client.get("/api/v1/admin/ops-summary", headers=_auth(admin_token)).json()

    db.add(
        Mt5Connection(
            user_id=client_user.id,
            broker_server="Demo-Server",
            login="12345",
            status=Mt5ConnectionStatus.DISCONNECTED.value,
        )
    )
    db.commit()

    after = client.get("/api/v1/admin/ops-summary", headers=_auth(admin_token)).json()
    assert after["mt5_disconnected_count"] == before["mt5_disconnected_count"] + 1
