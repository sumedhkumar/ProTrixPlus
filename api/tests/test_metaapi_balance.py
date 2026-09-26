"""GET /api/v1/me/mt5-connection/balance - real MetaApi balance reads, never
a fabricated number. Covers every "not available" reason plus a real
(mocked-HTTP) success path."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from protrix_contracts.db.models import User, UserRole

from app.config import get_settings
from app.services import metaapi_client

pytestmark = pytest.mark.dbtest


@pytest.fixture
def admin_token(db, identity):
    admin = User(
        email="balance-admin@example.test",
        display_name="BalanceAdmin",
        role=UserRole.SUPER_ADMIN.value,
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    return identity.issue(
        subject=str(admin.id),
        role=UserRole.SUPER_ADMIN,
        display_name="BalanceAdmin",
        email=admin.email,
    )


@pytest.fixture
def client_user(db):
    user = User(
        email="balance-client@example.test", display_name="BalanceClient", role=UserRole.USER.value
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
        display_name="BalanceClient",
        email=client_user.email,
    )


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_balance_unavailable_with_no_mt5_connection_at_all(
    client: TestClient, client_token: str
) -> None:
    r = client.get("/api/v1/me/mt5-connection/balance", headers=_auth(client_token))
    assert r.status_code == 200
    body = r.json()
    assert body["available"] is False
    assert "no MetaApi account" in body["reason"]
    assert "balance" not in body


def test_balance_unavailable_when_connection_exists_but_metaapi_not_attached(
    client: TestClient, client_token: str
) -> None:
    client.put(
        "/api/v1/me/mt5-connection",
        json={"broker_server": "MetaQuotes-Demo", "login": "123"},
        headers=_auth(client_token),
    )
    r = client.get("/api/v1/me/mt5-connection/balance", headers=_auth(client_token))
    assert r.status_code == 200
    body = r.json()
    assert body["available"] is False
    assert "no MetaApi account" in body["reason"]


def test_balance_unavailable_when_metaapi_token_not_configured(
    client: TestClient, admin_token, client_token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Admin token fixture not used for auth here, just to create a strategy-
    free path - the point is: metaapi_account_id is attached, but this
    deployment has no PROTRIX_METAAPI_TOKEN set, so it must say so honestly
    rather than attempt (and fail) a real call. Force this explicitly rather
    than relying on the ambient env being unset - a real token loaded from
    ../infra/.env (the actual live deployment's credential) previously made
    this test's "not configured" path execute for real against MetaApi,
    provisioning real, billed, orphaned accounts nothing in the DB ever
    referenced again."""
    monkeypatch.setenv("PROTRIX_METAAPI_TOKEN", "")
    get_settings.cache_clear()
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

    r = client.get("/api/v1/me/mt5-connection/balance", headers=_auth(client_token))
    assert r.status_code == 200
    body = r.json()
    assert body["available"] is False
    assert "not configured" in body["reason"]


def test_balance_returns_real_numbers_when_metaapi_call_succeeds(
    client: TestClient, admin_token, client_token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PROTRIX_METAAPI_TOKEN", "test-token")
    get_settings.cache_clear()

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

    def fake_get_account_information(*, token, region, account_id):  # noqa: ARG001
        assert token == "test-token"
        assert region == "london"
        assert account_id == "abc-123"
        return {"balance": 99815.85, "equity": 99815.85, "freeMargin": 99815.85, "currency": "USD"}

    monkeypatch.setattr(metaapi_client, "get_account_information", fake_get_account_information)

    r = client.get("/api/v1/me/mt5-connection/balance", headers=_auth(client_token))
    assert r.status_code == 200
    body = r.json()
    assert body["available"] is True
    assert body["balance"] == 99815.85
    assert body["currency"] == "USD"


def test_balance_unavailable_when_metaapi_call_fails(
    client: TestClient, admin_token, client_token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PROTRIX_METAAPI_TOKEN", "test-token")
    get_settings.cache_clear()

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

    def failing(*, token, region, account_id):  # noqa: ARG001
        raise metaapi_client.MetaApiError("MetaApi returned 500 for account abc-123")

    monkeypatch.setattr(metaapi_client, "get_account_information", failing)

    r = client.get("/api/v1/me/mt5-connection/balance", headers=_auth(client_token))
    assert r.status_code == 200
    body = r.json()
    assert body["available"] is False
    assert "500" in body["reason"]
