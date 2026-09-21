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


class MetaApiError(Exception):
    """A real MetaApi/network failure - distinct from "not connected yet"."""


def _client_api_host(region: str) -> str:
    return f"https://mt-client-api-v1.{region}.agiliumtrade.ai"


def _request(method: str, url: str, *, token: str, **kwargs: Any) -> dict[str, Any]:
    try:
        response = httpx.request(
            method,
            url,
            headers={"auth-token": token, "Accept": "application/json"},
            timeout=_TIMEOUT,
            **kwargs,
        )
    except (httpx.TimeoutException, httpx.TransportError) as exc:
        raise MetaApiError(f"MetaApi request failed ({method} {url}): {exc}") from exc

    if response.status_code >= 300:
        raise MetaApiError(f"MetaApi returned {response.status_code} for {method} {url}")

    if not response.content:
        return {}
    payload: dict[str, Any] = response.json()
    return payload


def get_account_information(*, token: str, region: str, account_id: str) -> dict[str, Any]:
    """Real balance/equity/margin for one client's connected MT5 account."""
    url = f"{_client_api_host(region)}/users/current/accounts/{account_id}/account-information"
    return _request("GET", url, token=token)


def create_account(
    *, token: str, name: str, server: str, region: str, magic: int, platform: str = "mt5"
) -> dict[str, Any]:
    """Provision a MetaApi account with no login/password - the client fills
    those in themselves via the configuration link (see below). Real,
    verified request shape: https://metaapi.cloud/docs/provisioning/api/account/createAccount/
    """
    url = f"{_PROVISIONING_HOST}/users/current/accounts"
    body = {"name": name, "server": server, "platform": platform, "region": region, "magic": magic}
    return _request("POST", url, token=token, json=body)


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
