"""POST /dev/login - mint fake claims for a seeded user. Local/CI only.

This is the *only* way to get a token in S0. It is disabled unless
``PROTRIX_DEV_IDENTITY_ENABLED`` is true, which must never be the case in prod.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from protrix_contracts.db.models import User, UserRole
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.identity import IdentityProvider
from app.security import get_identity_provider


class DevLoginRequest(BaseModel):
    role: UserRole = UserRole.USER
    subject: str | None = None  # specific user id; defaults to first of that role


class DevLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    subject: str
    role: UserRole
    display_name: str
    email: str


router = APIRouter(prefix="/dev", tags=["dev-identity"])


def _guard_enabled(settings: Settings = Depends(get_settings)) -> None:
    if not settings.dev_identity_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")


@router.post("/login", response_model=DevLoginResponse, dependencies=[Depends(_guard_enabled)])
def dev_login(
    body: DevLoginRequest,
    db: Session = Depends(get_db),
    provider: IdentityProvider = Depends(get_identity_provider),
) -> DevLoginResponse:
    stmt = select(User).where(User.is_active.is_(True))
    if body.subject:
        stmt = stmt.where(User.id == body.subject)
    else:
        stmt = stmt.where(User.role == body.role.value).order_by(User.created_at)
    user = db.scalars(stmt).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="no seeded user matches; run the seed",
        )
    if body.subject and user.role != body.role.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="requested subject does not have the requested role",
        )

    token = provider.issue(
        subject=str(user.id),
        role=UserRole(user.role),
        display_name=user.display_name,
        email=user.email,
    )
    return DevLoginResponse(
        access_token=token,
        subject=str(user.id),
        role=UserRole(user.role),
        display_name=user.display_name,
        email=user.email,
    )
