"""CredentialVault interface.

The vault is the system-of-record for broker credentials. Callers get a
:class:`ScopedCredentialHandle` - an opaque, expiring reference. The plaintext is
only ever materialised inside the execution adapter at the moment of a call, via
``use()``, and is never logged or returned across a process boundary.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol, runtime_checkable


class VaultError(Exception):
    pass


@dataclass(frozen=True)
class ScopedCredentialHandle:
    """A short-lived, scoped reference to a credential set.

    ``key_id`` and ``scope`` are safe to log. The secret values are NOT on this
    object - they are fetched just-in-time through the owning vault.
    """

    handle_id: str
    key_id: str
    scope: str
    expires_at: datetime
    _resolver: CredentialResolver = field(repr=False, compare=False)

    def is_expired(self, *, now: datetime | None = None) -> bool:
        return (now or datetime.now(UTC)) >= self.expires_at

    @contextmanager
    def use(self) -> Iterator[dict[str, str]]:
        """Yield the plaintext credential mapping for the lifetime of the block
        only. Never store, return, or log the yielded dict."""
        if self.is_expired():
            raise VaultError(f"credential handle {self.handle_id} expired")
        secret = self._resolver(self.handle_id)
        try:
            yield secret
        finally:
            secret.clear()

    def __str__(self) -> str:  # keeps f-strings / logs safe
        return f"<ScopedCredentialHandle key_id={self.key_id} scope={self.scope}>"


class CredentialResolver(Protocol):
    def __call__(self, handle_id: str) -> dict[str, str]: ...


@runtime_checkable
class CredentialVault(Protocol):
    def store_mt5_credentials(
        self,
        *,
        account_ref: str,
        login: str,
        password: str,
        server: str,
    ) -> str: ...

    def issue_handle(self, *, account_ref: str, scope: str) -> ScopedCredentialHandle: ...

    def revoke(self, handle_id: str) -> None: ...
