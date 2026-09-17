"""MockCredentialVault - fake secrets, keys separated from values.

Keys (``key_id``, ``scope``, ``account_ref``) live in one map; the fake secret
material lives in another, keyed only by an opaque ``handle_id``. Nothing here is
a real credential. ``issue_handle`` returns a handle with a short TTL; the
plaintext is only reachable through ``ScopedCredentialHandle.use()``.
"""

from __future__ import annotations

import secrets as _secrets
from datetime import UTC, datetime, timedelta

from app.vault.base import ScopedCredentialHandle, VaultError

_DEFAULT_TTL = timedelta(minutes=5)


class MockCredentialVault:
    def __init__(self, *, ttl: timedelta = _DEFAULT_TTL) -> None:
        self._ttl = ttl
        # keys, safe to log
        self._meta: dict[str, dict[str, str]] = {}
        # values, never logged, never returned by reference
        self._values: dict[str, dict[str, str]] = {}

    def store_mt5_credentials(
        self,
        *,
        account_ref: str,
        login: str,
        password: str,
        server: str,
    ) -> str:
        """Local-only in-memory vault store.

        It intentionally returns only an opaque key. Production must replace
        this class with a durable managed vault implementation.
        """
        if not login or not password or not server:
            raise VaultError("MT5 login, password, and server are required")
        key_id = "local-vault:" + _secrets.token_hex(12)
        self._meta[key_id] = {"key_id": key_id, "scope": "mt5", "account_ref": account_ref}
        self._values[key_id] = {"login": login, "password": password, "server": server}
        return key_id

    def issue_handle(self, *, account_ref: str, scope: str) -> ScopedCredentialHandle:
        handle_id = "vh_" + _secrets.token_hex(12)
        key_id = "kid_" + _secrets.token_hex(4)
        self._meta[handle_id] = {
            "key_id": key_id,
            "scope": scope,
            "account_ref": account_ref,
        }
        # Deterministic-looking but entirely fake material.
        self._values[handle_id] = {
            "metaapi_token": "FAKE." + _secrets.token_urlsafe(24),
            "metaapi_account_id": "fake-acct-" + _secrets.token_hex(6),
            "region": "fake-newyork",
        }
        return ScopedCredentialHandle(
            handle_id=handle_id,
            key_id=key_id,
            scope=scope,
            expires_at=datetime.now(UTC) + self._ttl,
            _resolver=self._resolve,
        )

    def revoke(self, handle_id: str) -> None:
        self._meta.pop(handle_id, None)
        self._values.pop(handle_id, None)

    def _resolve(self, handle_id: str) -> dict[str, str]:
        if handle_id not in self._values:
            raise VaultError("unknown or revoked credential handle")
        # Hand out a *copy*; ScopedCredentialHandle.use() clears it after the block.
        return dict(self._values[handle_id])
