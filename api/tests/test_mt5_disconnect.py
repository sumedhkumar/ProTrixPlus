"""DELETE /api/v1/me/mt5-connection - disconnecting locally used to leave the
real MetaApi account (a separately-billed resource) running forever, the
exact kind of orphan this session found and manually cleaned up.
Disconnecting now best-effort *undeploys* it on MetaApi too (stops the
running cloud terminal without deleting the account, so a later reconnect
redeploys it for free) - unless another user's connection still points at
the same account id, which is possible now that
connect_with_credentials/start_self_service_link reuse an existing account
for a shared broker login."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from protrix_contracts.db.models import User, UserRole

from app.config import get_settings
from app.services import metaapi_client

pytestmark = pytest.mark.dbtest


@pytest.fixture
def client_token(db, identity):
    user = User(email="disconnect-a@example.test", display_name="A", role=UserRole.USER.value)
    db.add(user)
    db.commit()
    db.refresh(user)
    return identity.issue(
        subject=str(user.id), role=UserRole.USER, display_name="A", email=user.email
    )


@pytest.fixture
def other_client_token(db, identity):
    user = User(email="disconnect-b@example.test", display_name="B", role=UserRole.USER.value)
    db.add(user)
    db.commit()
    db.refresh(user)
    return identity.issue(
        subject=str(user.id), role=UserRole.USER, display_name="B", email=user.email
    )


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_disconnect_with_no_connection_is_404(client: TestClient, client_token: str) -> None:
    r = client.delete("/api/v1/me/mt5-connection", headers=_auth(client_token))
    assert r.status_code == 404


def test_disconnect_with_no_metaapi_account_just_removes_locally(
    client: TestClient, client_token: str
) -> None:
    client.put(
        "/api/v1/me/mt5-connection",
        json={"broker_server": "MetaQuotes-Demo", "login": "123"},
        headers=_auth(client_token),
    )
    r = client.delete("/api/v1/me/mt5-connection", headers=_auth(client_token))
    assert r.status_code == 200
    body = r.json()
    assert body["metaapi_account_undeployed"] is False
    assert body["metaapi_error"] is None
    assert client.get("/api/v1/me/mt5-connection", headers=_auth(client_token)).json() is None


def test_disconnect_undeploys_the_metaapi_account_when_solely_owned(
    client: TestClient, client_token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PROTRIX_METAAPI_TOKEN", "test-token")
    get_settings.cache_clear()

    client.put(
        "/api/v1/me/mt5-connection",
        json={"broker_server": "MetaQuotes-Demo", "login": "555"},
        headers=_auth(client_token),
    )
    monkeypatch.setattr(metaapi_client, "find_account_id", lambda **kwargs: None)  # noqa: ARG005
    monkeypatch.setattr(metaapi_client, "create_account", lambda **kwargs: {"id": "solo-acct"})
    monkeypatch.setattr(
        metaapi_client,
        "create_configuration_link",
        lambda **kwargs: "https://x",  # noqa: ARG005
    )
    client.post(
        "/api/v1/me/mt5-connection/metaapi-link",
        json={"confirm_charge": True},
        headers=_auth(client_token),
    )

    undeployed = {"account_id": None}

    def fake_undeploy_account(*, token, account_id):  # noqa: ARG001
        undeployed["account_id"] = account_id

    monkeypatch.setattr(metaapi_client, "undeploy_account", fake_undeploy_account)

    r = client.delete("/api/v1/me/mt5-connection", headers=_auth(client_token))
    assert r.status_code == 200
    body = r.json()
    assert body["metaapi_account_undeployed"] is True
    assert body["metaapi_error"] is None
    assert undeployed["account_id"] == "solo-acct"


def test_disconnect_does_not_undeploy_an_account_shared_with_another_user(
    client: TestClient, client_token: str, other_client_token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both connections resolve to the same real broker login and were
    dedup-reused onto the same MetaApi account - undeploying it when one
    user disconnects must not break the other's still-active connection."""
    monkeypatch.setenv("PROTRIX_METAAPI_TOKEN", "test-token")
    get_settings.cache_clear()

    for token in (client_token, other_client_token):
        client.put(
            "/api/v1/me/mt5-connection",
            json={"broker_server": "MetaQuotes-Demo", "login": "shared-login"},
            headers=_auth(token),
        )

    monkeypatch.setattr(
        metaapi_client,
        "find_account_id",
        lambda **kwargs: "shared-acct",  # noqa: ARG005
    )
    monkeypatch.setattr(metaapi_client, "deploy_account", lambda **kwargs: None)  # noqa: ARG005
    monkeypatch.setattr(
        metaapi_client,
        "create_configuration_link",
        lambda **kwargs: "https://x",  # noqa: ARG005
    )

    def fail_if_called(**kwargs):  # noqa: ARG001
        raise AssertionError("create_account must not be called when an account already exists")

    monkeypatch.setattr(metaapi_client, "create_account", fail_if_called)
    client.post("/api/v1/me/mt5-connection/metaapi-link", headers=_auth(client_token))
    client.post("/api/v1/me/mt5-connection/metaapi-link", headers=_auth(other_client_token))

    def fail_if_undeployed(**kwargs):  # noqa: ARG001
        raise AssertionError("must not undeploy an account still used by another connection")

    monkeypatch.setattr(metaapi_client, "undeploy_account", fail_if_undeployed)

    r = client.delete("/api/v1/me/mt5-connection", headers=_auth(client_token))
    assert r.status_code == 200
    body = r.json()
    assert body["metaapi_account_undeployed"] is False
    assert "still used by another connection" in body["metaapi_error"]

    # The other user's connection is untouched.
    still_there = client.get("/api/v1/me/mt5-connection", headers=_auth(other_client_token)).json()
    assert still_there["metaapi_account_id"] == "shared-acct"


def test_disconnect_succeeds_locally_even_if_metaapi_undeploy_fails(
    client: TestClient, client_token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PROTRIX_METAAPI_TOKEN", "test-token")
    get_settings.cache_clear()

    client.put(
        "/api/v1/me/mt5-connection",
        json={"broker_server": "MetaQuotes-Demo", "login": "666"},
        headers=_auth(client_token),
    )
    monkeypatch.setattr(metaapi_client, "find_account_id", lambda **kwargs: None)  # noqa: ARG005
    monkeypatch.setattr(metaapi_client, "create_account", lambda **kwargs: {"id": "flaky-acct"})
    monkeypatch.setattr(
        metaapi_client,
        "create_configuration_link",
        lambda **kwargs: "https://x",  # noqa: ARG005
    )
    client.post(
        "/api/v1/me/mt5-connection/metaapi-link",
        json={"confirm_charge": True},
        headers=_auth(client_token),
    )

    def failing_undeploy(**kwargs):  # noqa: ARG001
        raise metaapi_client.MetaApiError("MetaApi returned 503 for POST .../undeploy")

    monkeypatch.setattr(metaapi_client, "undeploy_account", failing_undeploy)

    r = client.delete("/api/v1/me/mt5-connection", headers=_auth(client_token))
    assert r.status_code == 200
    body = r.json()
    assert body["metaapi_account_undeployed"] is False
    assert "503" in body["metaapi_error"]
    # Still disconnected locally despite the remote failure.
    assert client.get("/api/v1/me/mt5-connection", headers=_auth(client_token)).json() is None


def test_reconnect_after_soft_disconnect_redeploys_instead_of_recreating(
    client: TestClient, client_token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The end-to-end point of the whole feature: disconnect (undeploy),
    then reconnect with the same broker login - must redeploy the existing
    account, never provision (and re-bill for) a new one."""
    monkeypatch.setenv("PROTRIX_METAAPI_TOKEN", "test-token")
    get_settings.cache_clear()

    client.put(
        "/api/v1/me/mt5-connection",
        json={"broker_server": "MetaQuotes-Demo", "login": "777"},
        headers=_auth(client_token),
    )
    monkeypatch.setattr(metaapi_client, "find_account_id", lambda **kwargs: None)  # noqa: ARG005
    monkeypatch.setattr(metaapi_client, "create_account", lambda **kwargs: {"id": "persisted-acct"})
    monkeypatch.setattr(
        metaapi_client,
        "create_configuration_link",
        lambda **kwargs: "https://x",  # noqa: ARG005
    )
    client.post(
        "/api/v1/me/mt5-connection/metaapi-link",
        json={"confirm_charge": True},
        headers=_auth(client_token),
    )
    monkeypatch.setattr(metaapi_client, "undeploy_account", lambda **kwargs: None)  # noqa: ARG005
    client.delete("/api/v1/me/mt5-connection", headers=_auth(client_token))

    # Reconnect: broker server/login re-entered, same as before.
    client.put(
        "/api/v1/me/mt5-connection",
        json={"broker_server": "MetaQuotes-Demo", "login": "777"},
        headers=_auth(client_token),
    )

    def fail_if_created(**kwargs):  # noqa: ARG001
        raise AssertionError("must not create a new account - the old one should be redeployed")

    monkeypatch.setattr(metaapi_client, "create_account", fail_if_created)
    monkeypatch.setattr(
        metaapi_client,
        "find_account_id",
        lambda **kwargs: "persisted-acct",  # noqa: ARG005
    )

    redeployed = {"account_id": None}

    def fake_deploy_account(*, token, account_id):  # noqa: ARG001
        redeployed["account_id"] = account_id

    monkeypatch.setattr(metaapi_client, "deploy_account", fake_deploy_account)

    r = client.post("/api/v1/me/mt5-connection/metaapi-link", headers=_auth(client_token))
    assert r.status_code == 200
    assert r.json()["metaapi_account_id"] == "persisted-acct"
    assert redeployed["account_id"] == "persisted-acct"
