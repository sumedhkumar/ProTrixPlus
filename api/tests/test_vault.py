"""Invariant: the credential vault never hands plaintext to api/web/logs.

Only a short-lived, scoped handle crosses the boundary; the secret is reachable
only inside ``handle.use()`` and is cleared when that block exits.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.vault import MockCredentialVault, VaultError


def test_handle_exposes_metadata_but_not_secrets() -> None:
    vault = MockCredentialVault()
    handle = vault.issue_handle(account_ref="acct-1", scope="mt5:trade")

    assert handle.key_id.startswith("kid_")
    assert handle.scope == "mt5:trade"

    # Nothing secret in repr / str (what would land in a log line).
    for text in (repr(handle), str(handle)):
        assert "FAKE." not in text
        assert "metaapi_token" not in text


def test_secret_only_inside_use_and_is_cleared_after() -> None:
    vault = MockCredentialVault()
    handle = vault.issue_handle(account_ref="acct-1", scope="mt5:trade")

    with handle.use() as secret:
        assert secret["metaapi_token"].startswith("FAKE.")
        leaked = secret

    assert leaked == {}, "secret dict must be cleared when the use() block exits"


def test_expired_handle_refuses() -> None:
    vault = MockCredentialVault(ttl=timedelta(seconds=-1))
    handle = vault.issue_handle(account_ref="acct-1", scope="mt5:trade")
    assert handle.is_expired(now=datetime.now(UTC))
    with pytest.raises(VaultError), handle.use():
        pass


def test_revoked_handle_refuses() -> None:
    vault = MockCredentialVault()
    handle = vault.issue_handle(account_ref="acct-1", scope="mt5:trade")
    vault.revoke(handle.handle_id)
    with pytest.raises(VaultError), handle.use():
        pass
