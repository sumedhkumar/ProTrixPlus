"""metaapi_client.list_accounts / find_account_id - checking MetaApi's own
account list for an existing (login, server) match before provisioning a
new one. Added after a real, verified-live bug: two different local users
who shared the same real broker login each ended up with their own
separate (double-billed) MetaApi account for it, because account creation
only ever checked the local Mt5Connection row, never MetaApi's actual
account list."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from app.services import metaapi_client


class _FakeResponse:
    def __init__(self, status_code: int, payload: Any) -> None:
        self.status_code = status_code
        self._payload = payload
        self.content = b"x"

    def json(self) -> Any:
        return self._payload


def test_list_accounts_returns_the_raw_array(monkeypatch: pytest.MonkeyPatch) -> None:
    accounts = [
        {"_id": "a1", "login": "111", "server": "Broker-Demo", "state": "DEPLOYED"},
        {"_id": "a2", "login": "222", "server": "Broker-Demo", "state": "DEPLOYED"},
    ]
    monkeypatch.setattr(httpx, "get", lambda *a, **kw: _FakeResponse(200, accounts))  # noqa: ARG005
    assert metaapi_client.list_accounts(token="tok") == accounts


def test_list_accounts_raises_on_error_status(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(httpx, "get", lambda *a, **kw: _FakeResponse(500, {}))  # noqa: ARG005
    with pytest.raises(metaapi_client.MetaApiError):
        metaapi_client.list_accounts(token="tok")


def test_find_account_id_matches_on_login_and_server(monkeypatch: pytest.MonkeyPatch) -> None:
    accounts = [
        {"_id": "wrong-login", "login": "111", "server": "Broker-Demo", "state": "DEPLOYED"},
        {"_id": "wrong-server", "login": "222", "server": "Other-Demo", "state": "DEPLOYED"},
        {"_id": "right-one", "login": "222", "server": "Broker-Demo", "state": "DEPLOYED"},
    ]
    monkeypatch.setattr(metaapi_client, "list_accounts", lambda **kw: accounts)  # noqa: ARG005
    found = metaapi_client.find_account_id(token="tok", login="222", server="Broker-Demo")
    assert found == "right-one"


def test_find_account_id_returns_none_when_no_match(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(metaapi_client, "list_accounts", lambda **kw: [])  # noqa: ARG005
    assert metaapi_client.find_account_id(token="tok", login="999", server="Broker-Demo") is None


def test_find_account_id_prefers_a_deployed_duplicate(monkeypatch: pytest.MonkeyPatch) -> None:
    """Real observed state: the same (login, server) can already have more
    than one account provisioned (a pre-existing duplicate from this very
    bug) - prefer whichever one is actually DEPLOYED over an UNDEPLOYED
    leftover."""
    accounts = [
        {"_id": "stale", "login": "222", "server": "Broker-Demo", "state": "UNDEPLOYED"},
        {"_id": "live", "login": "222", "server": "Broker-Demo", "state": "DEPLOYED"},
    ]
    monkeypatch.setattr(metaapi_client, "list_accounts", lambda **kw: accounts)  # noqa: ARG005
    found = metaapi_client.find_account_id(token="tok", login="222", server="Broker-Demo")
    assert found == "live"


def test_find_account_id_handles_id_field_instead_of_underscore_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    accounts = [{"id": "created-shape", "login": "222", "server": "Broker-Demo"}]
    monkeypatch.setattr(metaapi_client, "list_accounts", lambda **kw: accounts)  # noqa: ARG005
    found = metaapi_client.find_account_id(token="tok", login="222", server="Broker-Demo")
    assert found == "created-shape"


def test_find_account_id_prefers_this_users_own_named_account_over_a_deployed_stranger(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A real, verified-live bug: two different local users shared the same
    real broker login, each with their own account. Without prefer_name,
    a user whose own account was UNDEPLOYED (soft-disconnected) got
    silently linked onto a *different* user's already-DEPLOYED account
    instead of their own - the exact opposite of what "prefer DEPLOYED"
    was meant to help with. Matching by name (create_account always names
    an account "protrixplus-{user_id}") must win regardless of deploy
    state."""
    accounts = [
        {
            "_id": "someone-elses-account",
            "login": "222",
            "server": "Broker-Demo",
            "state": "DEPLOYED",
            "name": "protrixplus-other-user-id",
        },
        {
            "_id": "my-own-account",
            "login": "222",
            "server": "Broker-Demo",
            "state": "UNDEPLOYED",
            "name": "protrixplus-me",
        },
    ]
    monkeypatch.setattr(metaapi_client, "list_accounts", lambda **kw: accounts)  # noqa: ARG005
    found = metaapi_client.find_account_id(
        token="tok", login="222", server="Broker-Demo", prefer_name="protrixplus-me"
    )
    assert found == "my-own-account"


def test_find_account_id_falls_back_to_prefer_deployed_when_no_name_matches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No account is named for this user at all (e.g. a pre-existing
    account nobody at ProTrixPlus created) - fall back to the old
    prefer-DEPLOYED heuristic rather than refusing to match anything."""
    accounts = [
        {"_id": "stale", "login": "222", "server": "Broker-Demo", "state": "UNDEPLOYED"},
        {"_id": "live", "login": "222", "server": "Broker-Demo", "state": "DEPLOYED"},
    ]
    monkeypatch.setattr(metaapi_client, "list_accounts", lambda **kw: accounts)  # noqa: ARG005
    found = metaapi_client.find_account_id(
        token="tok", login="222", server="Broker-Demo", prefer_name="protrixplus-nobody"
    )
    assert found == "live"


def test_delete_account_succeeds_on_204(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def fake_delete(url, *, headers, params, timeout):  # noqa: ARG001
        seen["url"] = url
        seen["params"] = params
        return _FakeResponse(204, None)

    monkeypatch.setattr(httpx, "delete", fake_delete)
    metaapi_client.delete_account(token="tok", account_id="acct-1")
    assert seen["url"].endswith("/users/current/accounts/acct-1")
    assert seen["params"] == {"executeForAllReplicas": "true"}


def test_delete_account_treats_404_as_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(httpx, "delete", lambda *a, **kw: _FakeResponse(404, {}))  # noqa: ARG005
    metaapi_client.delete_account(token="tok", account_id="already-gone")  # must not raise


def test_delete_account_raises_on_a_real_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(httpx, "delete", lambda *a, **kw: _FakeResponse(400, {}))  # noqa: ARG005
    with pytest.raises(metaapi_client.MetaApiError):
        metaapi_client.delete_account(token="tok", account_id="acct-1")


def test_undeploy_account_posts_to_the_undeploy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def fake_post(url, *, headers, timeout):  # noqa: ARG001
        seen["url"] = url
        return _FakeResponse(204, None)

    monkeypatch.setattr(httpx, "post", fake_post)
    metaapi_client.undeploy_account(token="tok", account_id="acct-1")
    assert seen["url"].endswith("/users/current/accounts/acct-1/undeploy")


def test_deploy_account_posts_to_the_deploy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def fake_post(url, *, headers, timeout):  # noqa: ARG001
        seen["url"] = url
        return _FakeResponse(204, None)

    monkeypatch.setattr(httpx, "post", fake_post)
    metaapi_client.deploy_account(token="tok", account_id="acct-1")
    assert seen["url"].endswith("/users/current/accounts/acct-1/deploy")


def test_lifecycle_action_raises_with_metaapi_error_detail(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        httpx,
        "post",
        lambda *a, **kw: _FakeResponse(400, {"message": "cannot deploy a deleted account"}),  # noqa: ARG005
    )
    with pytest.raises(metaapi_client.MetaApiError, match="cannot deploy a deleted account"):
        metaapi_client.deploy_account(token="tok", account_id="acct-1")
