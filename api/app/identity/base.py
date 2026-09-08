"""IdentityProvider interface + claims model."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from protrix_contracts.db.models import UserRole
from pydantic import BaseModel


class Claims(BaseModel):
    """Verified identity claims. This is what routes receive."""

    subject: str
    role: UserRole
    display_name: str
    email: str
    issued_at: datetime
    expires_at: datetime


class IdentityError(Exception):
    """Raised when a token is missing, malformed, expired, or untrusted."""


@runtime_checkable
class IdentityProvider(Protocol):
    """Issues and verifies identity tokens.

    A future ``OidcIdentityProvider`` implements this same Protocol; nothing
    outside this package changes.
    """

    def issue(self, *, subject: str, role: UserRole, display_name: str, email: str) -> str: ...

    def verify(self, token: str) -> Claims: ...
