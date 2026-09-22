"""POST /api/v1/me/mt5-connection/metaapi-link - real self-service MetaApi
onboarding. The client's MT5 password never passes through ProTrixPlus or an
admin - this only ever creates a passwordless account + a configuration link
MetaApi itself hosts."""

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
        email="link-client@example.test", display_name="LinkClient", role=UserRole.USER.value
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
        display_name="LinkClient",
        email=client_user.email,
    )


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_link_requires_a_broker_server_set_first(client: TestClient, client_token: str) -> None:
    r = client.post("/api/v1/me/mt5-connection/metaapi-link", headers=_auth(client_token))
    assert r.status_code == 404


def test_link_unavailable_when_metaapi_not_configured(
    client: TestClient, client_token: str
) -> None:
    client.put(
        "/api/v1/me/mt5-connection",
        json={"broker_server": "MetaQuotes-Demo", "login": "123"},
        headers=_auth(client_token),
    )
    r = client.post("/api/v1/me/mt5-connection/metaapi-link", headers=_auth(client_token))
    assert r.status_code == 503


def test_link_creates_a_passwordless_account_and_returns_the_real_link(
    client: TestClient, client_token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PROTRIX_METAAPI_TOKEN", "test-token")
    get_settings.cache_clear()

    client.put(
        "/api/v1/me/mt5-connection",
        json={"broker_server": "MetaQuotes-Demo", "login": "123"},
        headers=_auth(client_token),
    )

    seen_create: dict[str, object] = {}

    def fake_create_account(*, token, name, server, region, magic, platform="mt5"):
        # mt5_connection.start_self_service_link's call site never has a
        # password to pass in the first place (Mt5Connection has no password
        # column, by design) - this signature match is the real guarantee.
        seen_create.update(
            token=token, name=name, server=server, region=region, magic=magic, platform=platform
        )
        return {"id": "new-account-id-123"}

    def fake_create_configuration_link(*, token, account_id, ttl_days=7):
        assert account_id == "new-account-id-123"
        return "https://app.metaapi.cloud/configure-trading-account-credentials/abc"

    monkeypatch.setattr(metaapi_client, "create_account", fake_create_account)
    monkeypatch.setattr(metaapi_client, "create_configuration_link", fake_create_configuration_link)

    r = client.post("/api/v1/me/mt5-connection/metaapi-link", headers=_auth(client_token))
    assert r.status_code == 200
    body = r.json()
    assert body["configuration_link"] == (
        "https://app.metaapi.cloud/configure-trading-account-credentials/abc"
    )
    assert body["metaapi_account_id"] == "new-account-id-123"
    assert seen_create["server"] == "MetaQuotes-Demo"

    conn = client.get("/api/v1/me/mt5-connection", headers=_auth(client_token)).json()
    assert conn["metaapi_account_id"] == "new-account-id-123"
    assert conn["status"] == "PENDING"


def test_link_reuses_the_existing_account_instead_of_creating_a_second_one(
    client: TestClient, client_token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Calling this twice (e.g. the first link expired) must not create a
    second MetaApi account for the same client."""
    monkeypatch.setenv("PROTRIX_METAAPI_TOKEN", "test-token")
    get_settings.cache_clear()

    client.put(
        "/api/v1/me/mt5-connection",
        json={"broker_server": "MetaQuotes-Demo", "login": "123"},
        headers=_auth(client_token),
    )

    create_calls = {"count": 0}

    def fake_create_account(**kwargs):  # noqa: ARG001
        create_calls["count"] += 1
        return {"id": "only-once-id"}

    link_calls = {"count": 0}

    def fake_create_configuration_link(*, token, account_id, ttl_days=7):  # noqa: ARG001
        link_calls["count"] += 1
        return (
            f"https://app.metaapi.cloud/configure-trading-account-credentials/{link_calls['count']}"
        )

    monkeypatch.setattr(metaapi_client, "create_account", fake_create_account)
    monkeypatch.setattr(metaapi_client, "create_configuration_link", fake_create_configuration_link)

    first = client.post("/api/v1/me/mt5-connection/metaapi-link", headers=_auth(client_token))
    second = client.post("/api/v1/me/mt5-connection/metaapi-link", headers=_auth(client_token))

    assert first.json()["metaapi_account_id"] == "only-once-id"
    assert second.json()["metaapi_account_id"] == "only-once-id"
    assert create_calls["count"] == 1  # account created once
    assert link_calls["count"] == 2  # a fresh link each time is fine/expected


def test_check_connection_real_status_flips_to_connected(
    client: TestClient, client_token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PROTRIX_METAAPI_TOKEN", "test-token")
    get_settings.cache_clear()

    client.put(
        "/api/v1/me/mt5-connection",
        json={"broker_server": "MetaQuotes-Demo", "login": "123"},
        headers=_auth(client_token),
    )
    monkeypatch.setattr(
        metaapi_client,
        "create_account",
        lambda **kwargs: {"id": "acct-1"},  # noqa: ARG005
    )
    monkeypatch.setattr(
        metaapi_client,
        "create_configuration_link",
        lambda **kwargs: "https://app.metaapi.cloud/x",  # noqa: ARG005
    )
    client.post("/api/v1/me/mt5-connection/metaapi-link", headers=_auth(client_token))

    # Client hasn't finished yet.
    monkeypatch.setattr(
        metaapi_client,
        "get_account_status",
        lambda **kwargs: {"state": "DEPLOYED", "connectionStatus": "DISCONNECTED"},  # noqa: ARG005
    )
    still_pending = client.post(
        "/api/v1/me/mt5-connection/check", headers=_auth(client_token)
    ).json()
    assert still_pending["status"] == "PENDING"

    # Client finishes entering credentials on MetaApi's page.
    monkeypatch.setattr(
        metaapi_client,
        "get_account_status",
        lambda **kwargs: {"state": "DEPLOYED", "connectionStatus": "CONNECTED"},  # noqa: ARG005
    )
    monkeypatch.setattr(
        metaapi_client,
        "get_account_information",
        lambda **kwargs: {"balance": 1000},  # noqa: ARG005
    )
    now_connected = client.post(
        "/api/v1/me/mt5-connection/check", headers=_auth(client_token)
    ).json()
    assert now_connected["status"] == "CONNECTED"
    assert now_connected["last_error"] is None


def test_check_connection_surfaces_a_degraded_trading_api_without_flipping_status(
    client: TestClient, client_token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The broker-side terminal can be genuinely CONNECTED while MetaApi's
    own regional trading API is having an outage (a real MetaApi.cloud
    incident, not a bug in our code). `status` must stay CONNECTED - it's
    still true - but `last_error` should surface the degraded API so it's
    visible in the UI, not just in worker logs."""
    monkeypatch.setenv("PROTRIX_METAAPI_TOKEN", "test-token")
    get_settings.cache_clear()

    client.put(
        "/api/v1/me/mt5-connection",
        json={"broker_server": "MetaQuotes-Demo", "login": "123"},
        headers=_auth(client_token),
    )
    monkeypatch.setattr(
        metaapi_client,
        "create_account",
        lambda **kwargs: {"id": "acct-degraded"},  # noqa: ARG005
    )
    monkeypatch.setattr(
        metaapi_client,
        "create_configuration_link",
        lambda **kwargs: "https://app.metaapi.cloud/x",  # noqa: ARG005
    )
    client.post("/api/v1/me/mt5-connection/metaapi-link", headers=_auth(client_token))

    monkeypatch.setattr(
        metaapi_client,
        "get_account_status",
        lambda **kwargs: {"state": "DEPLOYED", "connectionStatus": "CONNECTED"},  # noqa: ARG005
    )

    def failing_account_information(**kwargs):  # noqa: ARG001
        raise metaapi_client.MetaApiError("MetaApi returned 503 for GET .../account-information")

    monkeypatch.setattr(metaapi_client, "get_account_information", failing_account_information)

    result = client.post("/api/v1/me/mt5-connection/check", headers=_auth(client_token)).json()
    assert result["status"] == "CONNECTED"
    assert result["last_error"] is not None
    assert "trading API is currently unavailable" in result["last_error"]
