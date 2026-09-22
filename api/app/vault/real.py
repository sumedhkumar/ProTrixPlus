"""RealCredentialVault - encrypted, persistent, real crypto.

Same job as :class:`~app.vault.mock.MockCredentialVault`, same
:class:`~app.vault.base.CredentialVault` shape, but the fake secret material
is encrypted at rest (Fernet: AES-128-CBC + HMAC, authenticated - not a
home-grown cipher) in the ``vault_secrets`` table instead of an in-memory
dict, so a handle survives a process restart and a tampered row is detected
rather than silently decrypted into garbage.

What makes it "real" is the persistence + encryption layer, not the secret
content: nothing calls a live broker yet (no MetaApi.cloud account is wired
in), so ``issue_handle`` still mints the same kind of synthetic
``metaapi_token=FAKE.…`` material the mock does - same honesty convention,
just durably protected instead of held in memory.
"""

from __future__ import annotations

import json
import secrets as _secrets
from datetime import UTC, datetime, timedelta

from cryptography.fernet import Fernet, InvalidToken
from protrix_contracts.db.models import VaultSecret
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.vault.base import ScopedCredentialHandle, VaultError

_DEFAULT_TTL = timedelta(minutes=5)


class RealCredentialVault:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        encryption_key: str,
        ttl: timedelta = _DEFAULT_TTL,
    ) -> None:
        # Fail closed, at construction - never lazily, never by silently
        # falling back to storing plaintext.
        try:
            self._fernet = Fernet(encryption_key.encode("utf-8"))
        except (ValueError, TypeError) as exc:
            raise VaultError(
                "invalid PROTRIX_VAULT_ENCRYPTION_KEY: must be a Fernet key "
                "(generate one with Fernet.generate_key())"
            ) from exc
        self._sf = session_factory
        self._ttl = ttl

    def issue_handle(self, *, account_ref: str, scope: str) -> ScopedCredentialHandle:
        handle_id = "vh_" + _secrets.token_hex(12)
        key_id = "kid_" + _secrets.token_hex(4)
        expires_at = datetime.now(UTC) + self._ttl

        # Deterministic-looking but entirely fake material - see module docstring.
        secret = {
            "metaapi_token": "FAKE." + _secrets.token_urlsafe(24),
            "metaapi_account_id": "fake-acct-" + _secrets.token_hex(6),
            "region": "fake-newyork",
        }
        ciphertext = self._fernet.encrypt(json.dumps(secret).encode("utf-8")).decode("ascii")

        with self._sf() as session:
            session.add(
                VaultSecret(
                    handle_id=handle_id,
                    key_id=key_id,
                    scope=scope,
                    account_ref=account_ref,
                    ciphertext=ciphertext,
                    expires_at=expires_at,
                )
            )
            session.commit()

        return ScopedCredentialHandle(
            handle_id=handle_id,
            key_id=key_id,
            scope=scope,
            expires_at=expires_at,
            _resolver=self._resolve,
        )

    def revoke(self, handle_id: str) -> None:
        with self._sf() as session:
            row = session.scalar(select(VaultSecret).where(VaultSecret.handle_id == handle_id))
            if row is not None:
                row.revoked_at = datetime.now(UTC)
                session.commit()

    def _resolve(self, handle_id: str) -> dict[str, str]:
        with self._sf() as session:
            row = session.scalar(select(VaultSecret).where(VaultSecret.handle_id == handle_id))
        if row is None or row.revoked_at is not None:
            raise VaultError("unknown or revoked credential handle")
        try:
            plaintext = self._fernet.decrypt(row.ciphertext.encode("ascii"))
        except InvalidToken as exc:
            raise VaultError(f"credential handle {handle_id} failed integrity check") from exc
        return json.loads(plaintext.decode("utf-8"))
