"""Authorization guard applied to every route.

``require_role`` is a FastAPI dependency factory. Routers either depend on it per
endpoint or list it in ``APIRouter(dependencies=[...])`` so a whole surface is
role-gated (the admin router does this).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from functools import lru_cache
from hmac import compare_digest

from fastapi import Depends, Header, HTTPException, Path, status
from protrix_contracts.db.models import User, UserRole, UserRoleGrant
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.identity import Claims, IdentityError, IdentityProvider, MockIdentityProvider


@lru_cache
def get_identity_provider() -> IdentityProvider:
    s = get_settings()
    return MockIdentityProvider(
        secret=s.dev_jwt_secret.get_secret_value(),
        issuer=s.dev_jwt_issuer,
        ttl_seconds=s.dev_jwt_ttl_seconds,
    )


def _bearer(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return authorization.split(" ", 1)[1].strip()


def current_claims(
    authorization: str | None = Header(default=None),
    provider: IdentityProvider = Depends(get_identity_provider),
    db: Session = Depends(get_db),
) -> Claims:
    token = _bearer(authorization)
    try:
        claims = provider.verify(token)
    except IdentityError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    # A deactivated account's outstanding tokens must stop working immediately
    # rather than staying valid until they expire - re-check against the DB on
    # every request. A token whose subject has no row at all is left alone (not
    # every caller of this dependency requires a persisted User).
    user = db.get(User, uuid.UUID(claims.subject))
    if user is not None and not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="account is inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return claims


def require_role(*roles: UserRole) -> Callable[..., Claims]:
    allowed = set(roles) or set(UserRole)

    def _guard(claims: Claims = Depends(current_claims), db: Session = Depends(get_db)) -> Claims:
        if claims.role in allowed:
            return claims
        # A user can hold extra admin roles beyond their primary claims.role
        # (see UserRoleGrant's docstring) - check those before rejecting.
        extra_roles = db.scalars(
            select(UserRoleGrant.role).where(UserRoleGrant.user_id == uuid.UUID(claims.subject))
        ).all()
        if any(UserRole(r) in allowed for r in extra_roles):
            return claims
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"role {claims.role.value} not permitted here",
        )

    return _guard


def webhook_authorized(
    x_webhook_token: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    """Mock stand-in for a signed TradingView source. Wrong/missing token -> 401,
    and the request never reaches persistence."""
    _require_webhook_token(
        x_webhook_token,
        settings.webhook_shared_secret.get_secret_value(),
    )


def tradingview_path_authorized(
    webhook_token: str = Path(..., min_length=16, max_length=256),
    settings: Settings = Depends(get_settings),
) -> None:
    """Authorize TradingView using a secret URL path segment.

    TradingView alert configuration supplies a URL and request body, but does
    not provide a UI for custom request headers. The path-secret route keeps
    the existing header-authenticated simulator route intact while providing a
    direct TradingView-compatible ingress.
    """
    _require_webhook_token(
        webhook_token,
        settings.tradingview_webhook_secret.get_secret_value(),
    )


def _require_webhook_token(provided: str | None, expected: str) -> None:
    if not expected or not provided or not compare_digest(provided, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="webhook not authorized"
        )
