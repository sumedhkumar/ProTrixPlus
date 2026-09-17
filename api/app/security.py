"""Authorization guard applied to every route.

``require_role`` is a FastAPI dependency factory. Routers either depend on it per
endpoint or list it in ``APIRouter(dependencies=[...])`` so a whole surface is
role-gated (the admin router does this).
"""

from __future__ import annotations

from collections.abc import Callable
from functools import lru_cache
from hmac import compare_digest

from fastapi import Depends, Header, HTTPException, Path, status
from protrix_contracts.db.models import UserRole

from app.config import Settings, get_settings
from app.identity import (
    Auth0IdentityProvider,
    Claims,
    IdentityError,
    IdentityProvider,
    MockIdentityProvider,
)


@lru_cache
def get_identity_provider() -> IdentityProvider:
    s = get_settings()
    if s.auth0_issuer:
        return Auth0IdentityProvider(s)
    if not s.dev_identity_enabled:
        raise IdentityError("no identity provider is configured")
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
) -> Claims:
    token = _bearer(authorization)
    try:
        return provider.verify(token)
    except IdentityError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def require_role(*roles: UserRole) -> Callable[..., Claims]:
    allowed = set(roles) or set(UserRole)

    def _guard(claims: Claims = Depends(current_claims)) -> Claims:
        if claims.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"role {claims.role.value} not permitted here",
            )
        return claims

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
