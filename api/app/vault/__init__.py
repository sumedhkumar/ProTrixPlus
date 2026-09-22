"""CredentialVault interface + implementations.

A future ``MetaApiExecutionAdapter`` will need broker credentials. Those come
from a :class:`~app.vault.base.CredentialVault` as a **short-lived scoped
handle** - never as plaintext returned to api / web / logs.
:class:`~app.vault.mock.MockCredentialVault` holds fake values in memory;
:class:`~app.vault.real.RealCredentialVault` is the same shape backed by
real encryption and DB persistence (still fake secret *content* until a real
MetaApi.cloud account is wired in - see its module docstring). Neither is
wired into the app yet; nothing calls ``issue_handle`` in production code.
"""

from app.vault.base import CredentialVault, ScopedCredentialHandle, VaultError
from app.vault.mock import MockCredentialVault
from app.vault.real import RealCredentialVault

__all__ = [
    "CredentialVault",
    "ScopedCredentialHandle",
    "VaultError",
    "MockCredentialVault",
    "RealCredentialVault",
]
