"""RealCredentialVault: same contract as the mock, backed by real encryption
and DB persistence. Requires a real PostgreSQL (dbtest) since it's a
DB-backed vault, unlike the in-memory mock.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from cryptography.fernet import Fernet
from protrix_contracts.db.models import VaultSecret
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.vault import RealCredentialVault, VaultError
from app.vault.base import ScopedCredentialHandle

pytestmark = pytest.mark.dbtest


@pytest.fixture
def vault_key() -> str:
    return Fernet.generate_key().decode("ascii")


@pytest.fixture
def session_factory(db_engine):
    return sessionmaker(bind=db_engine)


def test_handle_exposes_metadata_but_not_secrets(session_factory, vault_key: str) -> None:
    vault = RealCredentialVault(session_factory, encryption_key=vault_key)
    handle = vault.issue_handle(account_ref="acct-1", scope="mt5:trade")

    assert handle.key_id.startswith("kid_")
    assert handle.scope == "mt5:trade"
    for text in (repr(handle), str(handle)):
        assert "FAKE." not in text
        assert "metaapi_token" not in text


def test_secret_only_inside_use_and_is_cleared_after(session_factory, vault_key: str) -> None:
    vault = RealCredentialVault(session_factory, encryption_key=vault_key)
    handle = vault.issue_handle(account_ref="acct-1", scope="mt5:trade")

    with handle.use() as secret:
        assert secret["metaapi_token"].startswith("FAKE.")
        leaked = secret

    assert leaked == {}, "secret dict must be cleared when the use() block exits"


def test_expired_handle_refuses(session_factory, vault_key: str) -> None:
    vault = RealCredentialVault(
        session_factory, encryption_key=vault_key, ttl=timedelta(seconds=-1)
    )
    handle = vault.issue_handle(account_ref="acct-1", scope="mt5:trade")
    assert handle.is_expired(now=datetime.now(UTC))
    with pytest.raises(VaultError), handle.use():
        pass


def test_revoked_handle_refuses(session_factory, vault_key: str) -> None:
    vault = RealCredentialVault(session_factory, encryption_key=vault_key)
    handle = vault.issue_handle(account_ref="acct-1", scope="mt5:trade")
    vault.revoke(handle.handle_id)
    with pytest.raises(VaultError), handle.use():
        pass


def test_secret_survives_a_fresh_vault_instance(session_factory, vault_key: str) -> None:
    """Proves persistence, not just in-memory state like the mock."""
    vault_a = RealCredentialVault(session_factory, encryption_key=vault_key)
    original = vault_a.issue_handle(account_ref="acct-1", scope="mt5:trade")

    # A brand-new vault instance (fresh in-memory state, same DB + key) must
    # independently decrypt the row a completely different instance wrote.
    vault_b = RealCredentialVault(session_factory, encryption_key=vault_key)
    rehydrated_handle = ScopedCredentialHandle(
        handle_id=original.handle_id,
        key_id=original.key_id,
        scope=original.scope,
        expires_at=original.expires_at,
        _resolver=vault_b._resolve,
    )

    with original.use() as secret_a:
        copy_a = dict(secret_a)
    with rehydrated_handle.use() as secret_b:
        copy_b = dict(secret_b)

    assert copy_a == copy_b


def test_tampered_ciphertext_is_rejected_not_silently_decrypted(
    session_factory, vault_key: str
) -> None:
    vault = RealCredentialVault(session_factory, encryption_key=vault_key)
    handle = vault.issue_handle(account_ref="acct-1", scope="mt5:trade")

    with session_factory() as session:
        row = session.scalar(select(VaultSecret).where(VaultSecret.handle_id == handle.handle_id))
        row.ciphertext = row.ciphertext[:-4] + "abcd"
        session.commit()

    with pytest.raises(VaultError), handle.use():
        pass


def test_wrong_encryption_key_is_rejected_at_construction() -> None:
    with pytest.raises(VaultError):
        RealCredentialVault(sessionmaker(), encryption_key="not-a-valid-fernet-key")
