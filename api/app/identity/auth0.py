"""Auth0 RS256 access-token verifier."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from functools import cached_property
from typing import Any

import jwt
from protrix_contracts.db.models import UserRole

from app.config import Settings
from app.identity.base import Claims, IdentityError

_USER_NAMESPACE = uuid.UUID("da31c221-067b-4b9f-a9a0-2b3fbcaa1d11")


class Auth0IdentityProvider:
    """Verify an Auth0 token and expose a provider-neutral internal UUID."""

    def __init__(self, settings: Settings) -> None:
        if not settings.auth0_issuer or not settings.auth0_audience:
            raise IdentityError("Auth0 issuer and audience must be configured")
        self._issuer = settings.auth0_issuer.rstrip("/") + "/"
        self._audience = settings.auth0_audience
        self._role_claim = settings.auth0_role_claim
        self._email_claim = settings.auth0_email_claim
        self._name_claim = settings.auth0_name_claim

    @cached_property
    def _jwks(self) -> jwt.PyJWKClient:
        return jwt.PyJWKClient(f"{self._issuer}.well-known/jwks.json", cache_keys=True)

    def issue(self, *, subject: str, role: UserRole, display_name: str, email: str) -> str:
        raise IdentityError("Auth0 tokens are issued by Auth0")

    def verify(self, token: str) -> Claims:
        try:
            key = self._jwks.get_signing_key_from_jwt(token).key
            payload: dict[str, Any] = jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                audience=self._audience,
                issuer=self._issuer,
                options={"require": ["exp", "iat", "iss", "sub"]},
            )
        except jwt.PyJWTError as exc:
            raise IdentityError("invalid Auth0 access token") from exc
        raw_subject = str(payload["sub"])
        try:
            role = UserRole(str(payload.get(self._role_claim, UserRole.USER.value)))
        except ValueError as exc:
            raise IdentityError("invalid Auth0 role claim") from exc
        internal_subject = str(uuid.uuid5(_USER_NAMESPACE, raw_subject))
        email = str(
            payload.get(self._email_claim)
            or payload.get("email")
            or f"auth0-{internal_subject}@identity.invalid"
        )
        name = str(payload.get(self._name_claim) or payload.get("name") or email.split("@", 1)[0])
        return Claims(
            subject=internal_subject,
            role=role,
            display_name=name[:120],
            email=email[:320],
            issued_at=datetime.fromtimestamp(int(payload["iat"]), tz=UTC),
            expires_at=datetime.fromtimestamp(int(payload["exp"]), tz=UTC),
        )
