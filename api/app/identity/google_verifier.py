"""Verifies a Google Identity Services ID token (RS256, Google's JWKS).

This is deliberately *not* a second ``IdentityProvider`` (see identity/base.py):
Google never issues or verifies our own session JWTs, it only proves "this
person owns this email" once, up front, at signup/login time. Session tokens
still always come from ``get_identity_provider()`` in app/security.py.
"""

from __future__ import annotations

from dataclasses import dataclass

import jwt

_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
_ISSUERS = ("https://accounts.google.com", "accounts.google.com")

_jwk_client = jwt.PyJWKClient(_JWKS_URL)


class GoogleTokenError(Exception):
    """Raised when a Google credential is missing, malformed, untrusted, or
    the underlying Google account's email is not verified."""


@dataclass(frozen=True)
class GoogleIdentity:
    email: str
    name: str


def verify_google_id_token(credential: str, *, client_id: str) -> GoogleIdentity:
    if not client_id:
        raise GoogleTokenError("Google sign-in is not configured")

    try:
        signing_key = _jwk_client.get_signing_key_from_jwt(credential)
        decoded = jwt.decode(
            credential,
            signing_key.key,
            algorithms=["RS256"],
            audience=client_id,
            issuer=list(_ISSUERS),
            options={"require": ["exp", "iat", "iss", "sub", "email"]},
        )
    except jwt.InvalidTokenError as exc:
        raise GoogleTokenError(f"invalid Google credential: {exc}") from exc
    except jwt.PyJWKClientError as exc:
        raise GoogleTokenError(f"could not verify Google credential: {exc}") from exc

    if not decoded.get("email_verified"):
        raise GoogleTokenError("Google account email is not verified")

    email = str(decoded["email"]).lower()
    name = str(decoded.get("name") or email.split("@", 1)[0])
    return GoogleIdentity(email=email, name=name)
