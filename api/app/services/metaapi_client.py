"""MetaApi.cloud account-management calls made directly by the API service
(ADR-001).

Separate from ``worker/app/adapters/metaapi.py`` (which places real orders on
an already-connected account) - this module only ever provisions accounts and
reads their status, never trades. Two real hosts are involved:

* the provisioning host (``mt-provisioning-api-v1...``) - account lifecycle:
  create, read status, generate a client-facing configuration link. Not
  region-prefixed.
* the regional client-api host (``mt-client-api-v1.<region>...``) - live
  trading-terminal state for an already-connected account (balance/equity).
  Region-prefixed because that's where the account's cloud server actually
  runs.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

log = logging.getLogger("api.metaapi_client")

_PROVISIONING_HOST = "https://mt-provisioning-api-v1.agiliumtrade.agiliumtrade.ai"
_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0)
# Any call that makes MetaApi actually attempt to establish the broker
# connection before responding - creating an account WITH real credentials,
# or redeploying one that was undeployed - routinely takes longer than the
# default 10s read timeout (confirmed live for both: account creation
# earlier this session, and a deploy call timing out at the plain 10s
# _TIMEOUT just now). Every other call here only reads an already-known
# state and stays fast.
_BROKER_CONNECT_TIMEOUT = httpx.Timeout(connect=5.0, read=30.0, write=5.0, pool=5.0)


class MetaApiError(Exception):
    """A real MetaApi/network failure - distinct from "not connected yet"."""


def _client_api_host(region: str) -> str:
    return f"https://mt-client-api-v1.{region}.agiliumtrade.ai"


def _error_detail(response: httpx.Response) -> str:
    """MetaApi's error responses carry a real, specific ``message`` (e.g.
    "server X not found, did you mean Y") that's far more useful than the
    bare status code - always surface it instead of throwing it away."""
    try:
        body = response.json()
    except ValueError:
        return response.text[:300]
    message = body.get("message") if isinstance(body, dict) else None
    if isinstance(message, str):
        return message
    return str(body)[:300]


def _request(
    method: str, url: str, *, token: str, timeout: httpx.Timeout = _TIMEOUT, **kwargs: Any
) -> dict[str, Any]:
    try:
        response = httpx.request(
            method,
            url,
            headers={"auth-token": token, "Accept": "application/json"},
            timeout=timeout,
            **kwargs,
        )
    except (httpx.TimeoutException, httpx.TransportError) as exc:
        raise MetaApiError(f"MetaApi request failed ({method} {url}): {exc}") from exc

    if response.status_code >= 300:
        raise MetaApiError(
            f"MetaApi returned {response.status_code} for {method} {url}: "
            f"{_error_detail(response)}"
        )

    if not response.content:
        return {}
    payload: dict[str, Any] = response.json()
    return payload


def list_accounts(*, token: str) -> list[dict[str, Any]]:
    """Every MetaApi account already provisioned under this token.

    Used to check whether an account already exists for a given broker
    login/server *before* provisioning a new one - each account is a
    real, separately-billed MetaApi resource. Confirmed live: creating one
    per connection attempt without this check let two different local
    users who happened to share the same real broker login each get their
    own separate (duplicate, double-billed) MetaApi account for it.

    Unlike every other call here, this endpoint returns a bare JSON array,
    not an object, so it can't go through ``_request``.
    """
    url = f"{_PROVISIONING_HOST}/users/current/accounts"
    try:
        response = httpx.get(
            url, headers={"auth-token": token, "Accept": "application/json"}, timeout=_TIMEOUT
        )
    except (httpx.TimeoutException, httpx.TransportError) as exc:
        raise MetaApiError(f"MetaApi request failed (GET {url}): {exc}") from exc
    if response.status_code >= 300:
        raise MetaApiError(
            f"MetaApi returned {response.status_code} for GET {url}: {_error_detail(response)}"
        )
    payload = response.json()
    return payload if isinstance(payload, list) else []


def find_account_id(
    *, token: str, login: str, server: str, prefer_name: str | None = None
) -> str | None:
    """The id of an already-provisioned account for this exact broker
    login+server - None if there's no match at all.

    A real, verified-live bug: when more than one account already exists
    for the same login+server (exactly the duplicate situation this whole
    dedup feature exists to clean up), the first version of this function
    preferred whichever one happened to be DEPLOYED - which silently
    linked a *different* user's connection onto an already-active
    stranger's account instead of their own. create_account always names
    an account ``f"protrixplus-{user_id}"``; passing that same value as
    ``prefer_name`` here matches this user's own account by name first,
    regardless of its deploy state, and only falls back to "prefer
    DEPLOYED, else the first match" when no account is actually named for
    this user (e.g. a pre-existing account nobody at ProTrixPlus created).
    """
    matches = [
        a
        for a in list_accounts(token=token)
        if a.get("login") == login and a.get("server") == server
    ]
    if not matches:
        return None
    if prefer_name:
        exact = next((a for a in matches if a.get("name") == prefer_name), None)
        if exact:
            account_id = exact.get("id") or exact.get("_id")
            return str(account_id) if account_id else None
    deployed = next((a for a in matches if a.get("state") == "DEPLOYED"), None)
    chosen = deployed or matches[0]
    account_id = chosen.get("id") or chosen.get("_id")
    return str(account_id) if account_id else None


def delete_account(*, token: str, account_id: str) -> None:
    """Permanently remove a provisioned account - this is what actually
    stops it being billed, unlike just detaching our local pointer to it
    (see mt5_connection.disconnect_my_connection, which calls this).
    ``executeForAllReplicas=true`` is required by MetaApi whenever the
    account has region replicas, which every account here has by default;
    without it the request comes back 400. A 404 (already gone - e.g.
    someone deleted it by hand on the MetaApi dashboard) is treated as
    success, not an error - the end state we want is already true.
    """
    url = f"{_PROVISIONING_HOST}/users/current/accounts/{account_id}"
    try:
        response = httpx.delete(
            url,
            headers={"auth-token": token, "Accept": "application/json"},
            params={"executeForAllReplicas": "true"},
            timeout=_TIMEOUT,
        )
    except (httpx.TimeoutException, httpx.TransportError) as exc:
        raise MetaApiError(f"MetaApi request failed (DELETE {url}): {exc}") from exc
    if response.status_code >= 300 and response.status_code != 404:
        raise MetaApiError(
            f"MetaApi returned {response.status_code} for DELETE {url}: {_error_detail(response)}"
        )


def _lifecycle_action(
    *, token: str, account_id: str, action: str, timeout: httpx.Timeout = _TIMEOUT
) -> None:
    url = f"{_PROVISIONING_HOST}/users/current/accounts/{account_id}/{action}"
    try:
        response = httpx.post(
            url, headers={"auth-token": token, "Accept": "application/json"}, timeout=timeout
        )
    except (httpx.TimeoutException, httpx.TransportError) as exc:
        raise MetaApiError(f"MetaApi request failed (POST {url}): {exc}") from exc
    if response.status_code >= 300:
        raise MetaApiError(
            f"MetaApi returned {response.status_code} for POST {url}: {_error_detail(response)}"
        )


def undeploy_account(*, token: str, account_id: str) -> None:
    """Stop the account's running cloud trading terminal (what MetaApi
    actually bills for ongoing use) while keeping the account itself - its
    id, login, server, region - intact for a free redeploy later. This is
    the real "soft disconnect": unlike delete_account, nothing here is
    destroyed, so reconnecting the same broker login afterwards reuses this
    same account (via find_account_id + deploy_account) instead of
    provisioning - and re-billing for - a brand new one."""
    _lifecycle_action(token=token, account_id=account_id, action="undeploy")


def deploy_account(*, token: str, account_id: str) -> None:
    """Resume an account's cloud trading terminal - called when reconnecting
    onto an account found by find_account_id, since a soft-disconnected
    (undeployed) account needs to be told to start running again before it
    can actually reach the broker. Safe to call on an already-deployed
    account (idempotent no-op), confirmed live. Uses the longer broker-
    connect timeout - confirmed live, redeploying an undeployed account
    routinely takes longer than the default 10s read timeout, same as
    creating an account with real credentials."""
    _lifecycle_action(
        token=token, account_id=account_id, action="deploy", timeout=_BROKER_CONNECT_TIMEOUT
    )


def get_account_information(*, token: str, region: str, account_id: str) -> dict[str, Any]:
    """Real balance/equity/margin for one client's connected MT5 account."""
    url = f"{_client_api_host(region)}/users/current/accounts/{account_id}/account-information"
    return _request("GET", url, token=token)


def create_account(
    *,
    token: str,
    name: str,
    server: str,
    region: str,
    magic: int,
    platform: str = "mt5",
    login: str | None = None,
    password: str | None = None,
) -> dict[str, Any]:
    """Provision a MetaApi account. With no login/password, the client fills
    those in themselves via the configuration link (see below) - MetaApi
    never sees them from us. With login/password, we pass the client's real
    MT5 credentials straight through in this one request - never logged
    (httpx's default logging only records method/URL/status, never the
    body) and never persisted anywhere (no password column on our side).
    Real, verified request shape:
    https://metaapi.cloud/docs/provisioning/api/account/createAccount/
    """
    url = f"{_PROVISIONING_HOST}/users/current/accounts"
    body: dict[str, Any] = {
        "name": name,
        "server": server,
        "platform": platform,
        "region": region,
        "magic": magic,
    }
    if login:
        body["login"] = login
    if password:
        body["password"] = password
    timeout = _BROKER_CONNECT_TIMEOUT if password else _TIMEOUT
    return _request("POST", url, token=token, json=body, timeout=timeout)


def create_configuration_link(*, token: str, account_id: str, ttl_days: int = 7) -> str:
    """The real URL the client visits to enter their MT5 login/password
    directly with MetaApi - ProTrixPlus never sees it. Verified:
    https://metaapi.cloud/docs/provisioning/api/account/createConfigurationLink/
    """
    url = f"{_PROVISIONING_HOST}/users/current/accounts/{account_id}/configuration-link"
    result = _request("PUT", url, token=token, params={"ttlInDays": ttl_days})
    link = result.get("configurationLink")
    if not link:
        raise MetaApiError("MetaApi did not return a configurationLink")
    return str(link)


def get_account_status(*, token: str, account_id: str) -> dict[str, Any]:
    """``state`` (e.g. DEPLOYED) and ``connectionStatus`` (e.g. CONNECTED) for
    an account - used to detect that a client finished the configuration
    link without ProTrixPlus ever seeing their credentials."""
    url = f"{_PROVISIONING_HOST}/users/current/accounts/{account_id}"
    return _request("GET", url, token=token)
