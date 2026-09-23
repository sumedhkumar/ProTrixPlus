"""POST /api/v1/me/assignments/{id}/confirm-start - Setup Wizard step 3, the
explicit risk-disclosure "Start" gate. This is the only call that can move a
new admin grant from SETUP_INCOMPLETE to ACTIVE, and it must not be
skippable: the MT5-connected precondition is enforced server-side here, not
just by disabling a button in the UI.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from protrix_contracts.db.models import Mt5Connection, Mt5ConnectionStatus, User, UserRole
from sqlalchemy import select

from app.config import get_settings
from app.services import metaapi_client

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
    user = User(
        email="wizard-client@example.test", display_name="WizardClient", role=UserRole.USER.value
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def client_token(identity, client_user):
    return identity.issue(
        subject=str(client_user.id),
        role=UserRole.USER,
        display_name="WizardClient",
        email=client_user.email,
    )


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _grant(client: TestClient, admin_token: str, client_user, strategy_id: str) -> dict:
    return client.post(
        "/api/v1/admin/assignments",
        json={"user_id": str(client_user.id), "strategy_id": strategy_id, "master_lot": "1.00"},
        headers=_auth(admin_token),
    ).json()


def _strategy(client: TestClient, admin_token: str, key: str) -> dict:
    return client.post(
        "/api/v1/admin/strategies",
        json={"strategy_key": key, "strategy_version": "1.0", "name": key},
        headers=_auth(admin_token),
    ).json()


def test_new_grant_defaults_to_setup_incomplete(
    client: TestClient, admin_token, client_user
) -> None:
    strategy = _strategy(client, admin_token, "wiz-default")
    assignment = _grant(client, admin_token, client_user, strategy["id"])
    assert assignment["status"] == "SETUP_INCOMPLETE"
    assert assignment["confirmed_risk_disclosure"] is False
    assert assignment["activated_at"] is None


def test_re_granting_an_active_assignment_does_not_reset_its_status(
    client: TestClient, admin_token, client_user
) -> None:
    """An admin bumping master_lot for an already-active client must never
    silently pause their live trading by resetting status."""
    strategy = _strategy(client, admin_token, "wiz-regrant")
    assignment = _grant(client, admin_token, client_user, strategy["id"])

    # Directly flip to ACTIVE (simulating a completed setup) via the admin
    # override endpoint, then re-grant and confirm status survives untouched.
    client.patch(
        f"/api/v1/admin/assignments/{assignment['id']}",
        json={"status": "ACTIVE"},
        headers=_auth(admin_token),
    )
    regranted = _grant(client, admin_token, client_user, strategy["id"])
    assert regranted["status"] == "ACTIVE"


def test_confirm_start_requires_setup_incomplete_status(
    client: TestClient, admin_token, client_token, client_user
) -> None:
    strategy = _strategy(client, admin_token, "wiz-wrongstatus")
    assignment = _grant(client, admin_token, client_user, strategy["id"])
    client.patch(
        f"/api/v1/admin/assignments/{assignment['id']}",
        json={"status": "ACTIVE"},
        headers=_auth(admin_token),
    )

    r = client.post(
        f"/api/v1/me/assignments/{assignment['id']}/confirm-start", headers=_auth(client_token)
    )
    assert r.status_code == 422


def test_confirm_start_requires_mt5_connected(
    client: TestClient, admin_token, client_token, client_user
) -> None:
    strategy = _strategy(client, admin_token, "wiz-noconn")
    assignment = _grant(client, admin_token, client_user, strategy["id"])

    r = client.post(
        f"/api/v1/me/assignments/{assignment['id']}/confirm-start", headers=_auth(client_token)
    )
    assert r.status_code == 422


def test_confirm_start_happy_path(
    client: TestClient, admin_token, client_token, client_user, db
) -> None:
    strategy = _strategy(client, admin_token, "wiz-happy")
    assignment = _grant(client, admin_token, client_user, strategy["id"])

    client.put(
        "/api/v1/me/mt5-connection",
        json={"broker_server": "MetaQuotes-Demo", "login": "123"},
        headers=_auth(client_token),
    )
    conn = db.scalar(select(Mt5Connection).where(Mt5Connection.user_id == client_user.id))
    conn.status = Mt5ConnectionStatus.CONNECTED.value
    db.commit()

    r = client.post(
        f"/api/v1/me/assignments/{assignment['id']}/confirm-start", headers=_auth(client_token)
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ACTIVE"
    assert body["confirmed_risk_disclosure"] is True
    assert body["activated_at"] is not None

    # Not repeatable once already ACTIVE.
    again = client.post(
        f"/api/v1/me/assignments/{assignment['id']}/confirm-start", headers=_auth(client_token)
    )
    assert again.status_code == 422


def test_confirm_start_404_for_another_clients_assignment(
    client: TestClient, admin_token, client_token, client_user, db
) -> None:
    strategy = _strategy(client, admin_token, "wiz-isolation")
    other = User(email="wizard-other@example.test", display_name="Other", role=UserRole.USER.value)
    db.add(other)
    db.commit()
    db.refresh(other)
    assignment = _grant(client, admin_token, other, strategy["id"])

    r = client.post(
        f"/api/v1/me/assignments/{assignment['id']}/confirm-start", headers=_auth(client_token)
    )
    assert r.status_code == 404


def _connect_and_attach_metaapi(
    client: TestClient, admin_token: str, client_token: str, client_user, db
) -> None:
    set_r = client.put(
        "/api/v1/me/mt5-connection",
        json={"broker_server": "MetaQuotes-Demo", "login": "123"},
        headers=_auth(client_token),
    )
    connection_id = set_r.json()["id"]
    client.patch(
        f"/api/v1/admin/mt5-connections/{connection_id}/metaapi",
        json={"metaapi_account_id": "abc-123", "metaapi_region": "london"},
        headers=_auth(admin_token),
    )
    conn = db.scalar(select(Mt5Connection).where(Mt5Connection.user_id == client_user.id))
    conn.status = Mt5ConnectionStatus.CONNECTED.value
    db.commit()


def test_confirm_start_blocks_when_balance_below_strategy_minimum(
    client: TestClient,
    admin_token,
    client_token,
    client_user,
    db,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Strategy eligibility (this task): a strategy that declares
    min_balance must not go live on an MT5 account whose real balance is
    below it - enforced server-side in marketplace.confirm_start, not just
    as a UI warning."""
    monkeypatch.setenv("PROTRIX_METAAPI_TOKEN", "test-token")
    get_settings.cache_clear()

    strategy = client.post(
        "/api/v1/admin/strategies",
        json={
            "strategy_key": "wiz-minbal-low",
            "strategy_version": "1.0",
            "name": "wiz-minbal-low",
            "min_balance": "1000",
        },
        headers=_auth(admin_token),
    ).json()
    assert strategy["min_balance"] == "1000.00"
    assignment = _grant(client, admin_token, client_user, strategy["id"])
    _connect_and_attach_metaapi(client, admin_token, client_token, client_user, db)

    def low_balance(*, token, region, account_id):  # noqa: ARG001
        return {"balance": 50.0, "equity": 50.0, "freeMargin": 50.0, "currency": "USD"}

    monkeypatch.setattr(metaapi_client, "get_account_information", low_balance)

    r = client.post(
        f"/api/v1/me/assignments/{assignment['id']}/confirm-start", headers=_auth(client_token)
    )
    assert r.status_code == 422
    assert "minimum" in r.json()["detail"]


def test_confirm_start_allows_when_balance_meets_strategy_minimum(
    client: TestClient,
    admin_token,
    client_token,
    client_user,
    db,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PROTRIX_METAAPI_TOKEN", "test-token")
    get_settings.cache_clear()

    strategy = client.post(
        "/api/v1/admin/strategies",
        json={
            "strategy_key": "wiz-minbal-ok",
            "strategy_version": "1.0",
            "name": "wiz-minbal-ok",
            "min_balance": "1000",
        },
        headers=_auth(admin_token),
    ).json()
    assignment = _grant(client, admin_token, client_user, strategy["id"])
    _connect_and_attach_metaapi(client, admin_token, client_token, client_user, db)

    def ample_balance(*, token, region, account_id):  # noqa: ARG001
        return {"balance": 5000.0, "equity": 5000.0, "freeMargin": 5000.0, "currency": "USD"}

    monkeypatch.setattr(metaapi_client, "get_account_information", ample_balance)

    r = client.post(
        f"/api/v1/me/assignments/{assignment['id']}/confirm-start", headers=_auth(client_token)
    )
    assert r.status_code == 200
    assert r.json()["status"] == "ACTIVE"


def test_confirm_start_not_blocked_when_balance_unverifiable(
    client: TestClient, admin_token, client_token, client_user, db
) -> None:
    """No PROTRIX_METAAPI_TOKEN configured (default test env) - balance is
    unknown, not below minimum, so activation must not be blocked on a fact
    we can't actually verify (mirrors mt5_connection's honesty rule)."""
    strategy = client.post(
        "/api/v1/admin/strategies",
        json={
            "strategy_key": "wiz-minbal-unverifiable",
            "strategy_version": "1.0",
            "name": "wiz-minbal-unverifiable",
            "min_balance": "1000",
        },
        headers=_auth(admin_token),
    ).json()
    assignment = _grant(client, admin_token, client_user, strategy["id"])
    _connect_and_attach_metaapi(client, admin_token, client_token, client_user, db)

    r = client.post(
        f"/api/v1/me/assignments/{assignment['id']}/confirm-start", headers=_auth(client_token)
    )
    assert r.status_code == 200
    assert r.json()["status"] == "ACTIVE"
