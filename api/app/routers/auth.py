"""POST /auth/signup, POST /auth/login - real client authentication (PRD 5.1).

Distinct from /dev/login (mock, no password, dev/CI only - see dev_identity.py).
This is the actual signup/login path clients use. Admin accounts are seeded
directly (not self-signup) and log in through this same /auth/login endpoint
once given a password by whoever provisions them.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from protrix_contracts.db.models import User, UserRole
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import hash_password, verify_password
from app.db import get_db
from app.identity import IdentityProvider
from app.security import get_identity_provider

router = APIRouter(prefix="/auth", tags=["auth"])

# Deliberately simple (not RFC 5322): good enough to reject obvious garbage
# without pulling in a new dependency (email-validator isn't installed here).
_EMAIL_RE = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class SignupRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320, pattern=_EMAIL_RE)
    password: str = Field(min_length=8, max_length=256)
    display_name: str = Field(min_length=1, max_length=120)

    @field_validator("email")
    @classmethod
    def _lower(cls, v: str) -> str:
        return v.lower()


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=256)

    @field_validator("email")
    @classmethod
    def _lower(cls, v: str) -> str:
        return v.lower()


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    subject: str
    role: UserRole
    display_name: str
    email: str


@router.post("/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def signup(
    body: SignupRequest,
    db: Session = Depends(get_db),
    provider: IdentityProvider = Depends(get_identity_provider),
) -> AuthResponse:
    user = User(
        email=body.email,
        display_name=body.display_name,
        role=UserRole.USER.value,
        is_active=True,
        password_hash=hash_password(body.password),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="an account with this email already exists"
        ) from exc
    db.refresh(user)

    token = provider.issue(
        subject=str(user.id),
        role=UserRole(user.role),
        display_name=user.display_name,
        email=user.email,
    )
    return AuthResponse(
        access_token=token,
        subject=str(user.id),
        role=UserRole(user.role),
        display_name=user.display_name,
        email=user.email,
    )


@router.post("/login", response_model=AuthResponse)
def login(
    body: LoginRequest,
    db: Session = Depends(get_db),
    provider: IdentityProvider = Depends(get_identity_provider),
) -> AuthResponse:
    user = db.scalar(select(User).where(User.email == body.email))

    # Constant-shape failure: wrong email and wrong password both 401, and we
    # still run verify_password against *something* even on a lookup miss so
    # response timing doesn't leak whether the email exists.
    password_ok = verify_password(body.password, user.password_hash if user else None)
    if user is None or not user.is_active or not password_ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid email or password"
        )

    token = provider.issue(
        subject=str(user.id),
        role=UserRole(user.role),
        display_name=user.display_name,
        email=user.email,
    )
    return AuthResponse(
        access_token=token,
        subject=str(user.id),
        role=UserRole(user.role),
        display_name=user.display_name,
        email=user.email,
    )
