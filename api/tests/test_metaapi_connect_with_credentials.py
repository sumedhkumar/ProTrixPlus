"""POST /api/v1/me/mt5-connection/connect - direct-entry MT5 onboarding. The
client's real MT5 password is submitted here and forwarded straight to
MetaApi's account-creation call - never written to the database (no
password column exists on Mt5Connection) and never logged."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from protrix_contracts.db.models import User, UserRole

from app.config import get_settings
from app.services import metaapi_client

pytestmark = pytest.mark.dbtest


@pytest.fixture
def client_user(db):
    user = User(
        email="connect-client@example.test", display_name="ConnectClient", role=UserRole.USER.value
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
        display_name="ConnectClient",
        email=client_user.email,
    )


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_connect_requires_broker_and_login_set_first(client: TestClient, client_token: str) -> None:
    r = client.post(
        "/api/v1/me/mt5-connection/connect",
        json={"password": "s3cret"},
        headers=_auth(client_token),
    )
    assert r.status_code == 404


def test_connect_unavailable_when_metaapi_not_configured(
    client: TestClient, client_token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Force this explicitly rather than relying on the ambient env being
    # unset - a real token loaded from ../infra/.env previously made this
    # "not configured" path run for real against MetaApi, provisioning real,
    # billed, orphaned accounts nothing in the DB ever referenced again.
    monkeypatch.setenv("PROTRIX_METAAPI_TOKEN", "")
    get_settings.cache_clear()
    client.put(
        "/api/v1/me/mt5-connection",
        json={"broker_server": "MetaQuotes-Demo", "login": "123"},
        headers=_auth(client_token),
    )
    r = client.post(
        "/api/v1/me/mt5-connection/connect",
        json={"password": "s3cret"},
        headers=_auth(client_token),
    )
    assert r.status_code == 503


def test_connect_sends_real_credentials_to_metaapi_and_never_stores_the_password(
    client: TestClient, client_token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PROTRIX_METAAPI_TOKEN", "test-token")
    get_settings.cache_clear()

    client.put(
        "/api/v1/me/mt5-connection",
        json={"broker_server": "MetaQuotes-Demo", "login": "555444"},
        headers=_auth(client_token),
    )

    seen_create: dict[str, object] = {}

    def fake_create_account(
        *, token, name, server, region, magic, platform="mt5", login=None, password=None
    ):
        seen_create.update(
            token=token,
            name=name,
            server=server,
            region=region,
            magic=magic,
            login=login,
            password=password,
        )
        return {"id": "creds-account-1"}

    monkeypatch.setattr(metaapi_client, "find_account_id", lambda **kwargs: None)  # noqa: ARG005
    monkeypatch.setattr(metaapi_client, "create_account", fake_create_account)
    monkeypatch.setattr(
        metaapi_client,
        "get_account_status",
        lambda **kwargs: {"state": "DEPLOYING", "connectionStatus": "DISCONNECTED"},  # noqa: ARG005
    )

    r = client.post(
        "/api/v1/me/mt5-connection/connect",
        json={"password": "my-real-mt5-password", "confirm_charge": True},
        headers=_auth(client_token),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["metaapi_account_id"] == "creds-account-1"
    # The real credentials really were forwarded to MetaApi's create_account call.
    assert seen_create["login"] == "555444"
    assert seen_create["password"] == "my-real-mt5-password"
    assert seen_create["server"] == "MetaQuotes-Demo"

    # Never persisted: no password field exists on the stored connection at all.
    conn = client.get("/api/v1/me/mt5-connection", headers=_auth(client_token)).json()
    assert "password" not in conn
    assert conn["metaapi_account_id"] == "creds-account-1"


def test_connect_requires_confirm_charge_before_creating_a_new_account(
    client: TestClient, client_token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Provisioning a brand new account is real money - never silent, and
    never bypassable just because some future button forgets to check
    would_create_new_account first. The server itself refuses without an
    explicit confirm_charge=true."""
    monkeypatch.setenv("PROTRIX_METAAPI_TOKEN", "test-token")
    get_settings.cache_clear()

    client.put(
        "/api/v1/me/mt5-connection",
        json={"broker_server": "MetaQuotes-Demo", "login": "111222"},
        headers=_auth(client_token),
    )

    def fail_if_called(**kwargs):  # noqa: ARG001
        raise AssertionError("create_account must not be called without confirm_charge")

    monkeypatch.setattr(metaapi_client, "find_account_id", lambda **kwargs: None)  # noqa: ARG005
    monkeypatch.setattr(metaapi_client, "create_account", fail_if_called)

    r = client.post(
        "/api/v1/me/mt5-connection/connect",
        json={"password": "pw"},
        headers=_auth(client_token),
    )
    assert r.status_code == 409


def test_connect_reuses_an_account_metaapi_already_has_for_this_login(
    client: TestClient, client_token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A real, verified-live bug: two different local users who happened to
    share the same real broker login each got their own separate (double-
    billed) MetaApi account for it, because the old code only checked
    *this connection row*, never MetaApi's own account list, before
    creating. find_account_id now checks that list first."""
    monkeypatch.setenv("PROTRIX_METAAPI_TOKEN", "test-token")
    get_settings.cache_clear()

    client.put(
        "/api/v1/me/mt5-connection",
        json={"broker_server": "MetaQuotes-Demo", "login": "555444"},
        headers=_auth(client_token),
    )

    def fail_if_called(**kwargs):  # noqa: ARG001
        raise AssertionError("create_account must not be called when an account already exists")

    monkeypatch.setattr(
        metaapi_client,
        "find_account_id",
        lambda **kwargs: "already-existing-account-id",  # noqa: ARG005
    )
    monkeypatch.setattr(metaapi_client, "create_account", fail_if_called)
    monkeypatch.setattr(metaapi_client, "deploy_account", lambda **kwargs: None)  # noqa: ARG005
    monkeypatch.setattr(
        metaapi_client,
        "get_account_status",
        lambda **kwargs: {"state": "DEPLOYED", "connectionStatus": "CONNECTED"},  # noqa: ARG005
    )
    monkeypatch.setattr(
        metaapi_client,
        "get_account_information",
        lambda **kwargs: {"balance": 500},  # noqa: ARG005
    )

    r = client.post(
        "/api/v1/me/mt5-connection/connect",
        json={"password": "whatever"},
        headers=_auth(client_token),
    )
    assert r.status_code == 200
    assert r.json()["metaapi_account_id"] == "already-existing-account-id"


def test_connect_reuses_existing_account_instead_of_recreating(
    client: TestClient, client_token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PROTRIX_METAAPI_TOKEN", "test-token")
    get_settings.cache_clear()

    client.put(
        "/api/v1/me/mt5-connection",
        json={"broker_server": "MetaQuotes-Demo", "login": "999"},
        headers=_auth(client_token),
    )

    create_calls = {"count": 0}

    def fake_create_account(**kwargs):  # noqa: ARG001
        create_calls["count"] += 1
        return {"id": "only-once-creds-id"}

    monkeypatch.setattr(metaapi_client, "find_account_id", lambda **kwargs: None)  # noqa: ARG005
    monkeypatch.setattr(metaapi_client, "create_account", fake_create_account)
    monkeypatch.setattr(
        metaapi_client,
        "get_account_status",
        lambda **kwargs: {"state": "DEPLOYED", "connectionStatus": "CONNECTED"},  # noqa: ARG005
    )
    monkeypatch.setattr(
        metaapi_client,
        "get_account_information",
        lambda **kwargs: {"balance": 500},  # noqa: ARG005
    )

    first = client.post(
        "/api/v1/me/mt5-connection/connect",
        json={"password": "pw1", "confirm_charge": True},
        headers=_auth(client_token),
    )
    second = client.post(
        "/api/v1/me/mt5-connection/connect",
        json={"password": "pw2"},
        headers=_auth(client_token),
    )
    assert first.json()["metaapi_account_id"] == "only-once-creds-id"
    assert second.json()["metaapi_account_id"] == "only-once-creds-id"
    assert create_calls["count"] == 1
    assert second.json()["status"] == "CONNECTED"


def test_would_create_new_account_requires_broker_and_login_set_first(
    client: TestClient, client_token: str
) -> None:
    r = client.post(
        "/api/v1/me/mt5-connection/would-create-new-account", headers=_auth(client_token)
    )
    assert r.status_code == 404


def test_would_create_new_account_unavailable_when_metaapi_not_configured(
    client: TestClient, client_token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PROTRIX_METAAPI_TOKEN", "")
    get_settings.cache_clear()
    client.put(
        "/api/v1/me/mt5-connection",
        json={"broker_server": "MetaQuotes-Demo", "login": "123"},
        headers=_auth(client_token),
    )
    r = client.post(
        "/api/v1/me/mt5-connection/would-create-new-account", headers=_auth(client_token)
    )
    assert r.status_code == 503


def test_would_create_new_account_true_when_no_existing_account_found(
    client: TestClient, client_token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PROTRIX_METAAPI_TOKEN", "test-token")
    get_settings.cache_clear()
    client.put(
        "/api/v1/me/mt5-connection",
        json={"broker_server": "MetaQuotes-Demo", "login": "999888"},
        headers=_auth(client_token),
    )
    monkeypatch.setattr(metaapi_client, "find_account_id", lambda **kwargs: None)  # noqa: ARG005

    r = client.post(
        "/api/v1/me/mt5-connection/would-create-new-account", headers=_auth(client_token)
    )
    assert r.status_code == 200
    assert r.json() == {"will_create_new_account": True}


def test_would_create_new_account_false_when_metaapi_already_has_a_matching_account(
    client: TestClient, client_token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PROTRIX_METAAPI_TOKEN", "test-token")
    get_settings.cache_clear()
    client.put(
        "/api/v1/me/mt5-connection",
        json={"broker_server": "MetaQuotes-Demo", "login": "999888"},
        headers=_auth(client_token),
    )
    monkeypatch.setattr(
        metaapi_client,
        "find_account_id",
        lambda **kwargs: "already-there-id",  # noqa: ARG005
    )

    r = client.post(
        "/api/v1/me/mt5-connection/would-create-new-account", headers=_auth(client_token)
    )
    assert r.status_code == 200
    assert r.json() == {"will_create_new_account": False}


def test_would_create_new_account_false_when_connection_already_has_one_attached(
    client: TestClient, client_token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Once a connection already has metaapi_account_id set, connect_with_
    credentials skips the create/find step entirely - so the preview must
    say False without even calling find_account_id."""
    monkeypatch.setenv("PROTRIX_METAAPI_TOKEN", "test-token")
    get_settings.cache_clear()
    client.put(
        "/api/v1/me/mt5-connection",
        json={"broker_server": "MetaQuotes-Demo", "login": "777666"},
        headers=_auth(client_token),
    )

    # First connect call: no account attached yet, so find_account_id
    # legitimately runs (and finds nothing) before create_account attaches one.
    monkeypatch.setattr(metaapi_client, "find_account_id", lambda **kwargs: None)  # noqa: ARG005
    monkeypatch.setattr(metaapi_client, "create_account", lambda **kwargs: {"id": "attach-id"})  # noqa: ARG005
    monkeypatch.setattr(
        metaapi_client,
        "get_account_status",
        lambda **kwargs: {"state": "DEPLOYED", "connectionStatus": "CONNECTED"},  # noqa: ARG005
    )
    monkeypatch.setattr(
        metaapi_client,
        "get_account_information",
        lambda **kwargs: {"balance": 500},  # noqa: ARG005
    )
    client.post(
        "/api/v1/me/mt5-connection/connect",
        json={"password": "pw", "confirm_charge": True},
        headers=_auth(client_token),
    )

    def fail_if_called(**kwargs):  # noqa: ARG001
        raise AssertionError("find_account_id must not be called - account already attached")

    monkeypatch.setattr(metaapi_client, "find_account_id", fail_if_called)

    r = client.post(
        "/api/v1/me/mt5-connection/would-create-new-account", headers=_auth(client_token)
    )
    assert r.status_code == 200
    assert r.json() == {"will_create_new_account": False}
