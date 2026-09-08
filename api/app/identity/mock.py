"""MockIdentityProvider - HS256 signed fake claims. Local/CI only."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
from protrix_contracts.db.models import UserRole

from app.identity.base import Claims, IdentityError, IdentityProvider

_ALGO = "HS256"


class MockIdentityProvider(IdentityProvider):
    def __init__(self, *, secret: str, issuer: str, ttl_seconds: int) -> None:
        self._secret = secret
        self._issuer = issuer
        self._ttl = timedelta(seconds=ttl_seconds)

    def issue(self, *, subject: str, role: UserRole, display_name: str, email: str) -> str:
        now = datetime.now(UTC)
        payload = {
            "sub": subject,
            "role": UserRole(role).value,
            "name": display_name,
            "email": email,
            "iss": self._issuer,
            "iat": int(now.timestamp()),
            "exp": int((now + self._ttl).timestamp()),
        }
        return jwt.encode(payload, self._secret, algorithm=_ALGO)

    def verify(self, token: str) -> Claims:
        try:
            decoded = jwt.decode(
                token,
                self._secret,
                algorithms=[_ALGO],
                issuer=self._issuer,
                options={"require": ["exp", "iat", "iss", "sub", "role"]},
            )
        except jwt.InvalidTokenError as exc:
            raise IdentityError(f"invalid token: {exc}") from exc

        try:
            role = UserRole(decoded["role"])
        except ValueError as exc:
            raise IdentityError(f"unknown role: {decoded.get('role')!r}") from exc

        return Claims(
            subject=str(decoded["sub"]),
            role=role,
            display_name=str(decoded.get("name", "")),
            email=str(decoded.get("email", "")),
            issued_at=datetime.fromtimestamp(decoded["iat"], tz=UTC),
            expires_at=datetime.fromtimestamp(decoded["exp"], tz=UTC),
        )
