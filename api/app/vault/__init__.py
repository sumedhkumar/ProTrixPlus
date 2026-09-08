"""CredentialVault interface + mock.

A future ``MetaApiExecutionAdapter`` will need broker credentials. Those come
from a :class:`~app.vault.base.CredentialVault` as a **short-lived scoped
handle** - never as plaintext returned to api / web / logs. Only
:class:`~app.vault.mock.MockCredentialVault` exists today; it holds fake values,
stores keys separately from values, and never returns the secret material.
"""

from app.vault.base import CredentialVault, ScopedCredentialHandle, VaultError
from app.vault.mock import MockCredentialVault

__all__ = [
    "CredentialVault",
    "ScopedCredentialHandle",
    "VaultError",
    "MockCredentialVault",
]
