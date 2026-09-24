"""POST /auth/signup, POST /auth/login - real client authentication (PRD 5.1).

Distinct from /dev/login (mock, no password, dev/CI only - see dev_identity.py).
This is the actual signup/login path clients use. Admin accounts are seeded
directly (not self-signup) and log in through this same /auth/login endpoint
once given a password by whoever provisions them.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from protrix_contracts.db.models import AdminInvite, PasswordResetToken, User, UserRole
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import hash_password, verify_password
from app.config import Settings, get_settings
from app.db import get_db
from app.email import EmailSender, get_email_sender
from app.identity import Claims, IdentityProvider
from app.identity.google_verifier import GoogleTokenError, verify_google_id_token
from app.security import current_claims, get_identity_provider
from app.services import notifications, subscriptions

router = APIRouter(prefix="/auth", tags=["auth"])

_RESET_TOKEN_TTL = timedelta(hours=1)

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
    must_change_password: bool = False


class SignupTrialRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=320, pattern=_EMAIL_RE)
    # Not collected on the free-trial form for now (may come back as a
    # settings-page addition later) - nullable to match User.phone.
    phone: str | None = Field(default=None, max_length=32)

    @field_validator("email")
    @classmethod
    def _lower(cls, v: str) -> str:
        return v.lower()


class SignupTrialResponse(BaseModel):
    email: str
    message: str = "Account created. Check your email for a temporary password."


class GoogleAuthRequest(BaseModel):
    credential: str = Field(min_length=1)


class SetPasswordRequest(BaseModel):
    new_password: str = Field(min_length=8, max_length=256)


class ForgotPasswordRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)


class ForgotPasswordResponse(BaseModel):
    detail: str = "If that email exists, a reset link has been sent."


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=1)
    new_password: str = Field(min_length=8, max_length=256)


@router.post("/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def signup(
    body: SignupRequest,
    db: Session = Depends(get_db),
    provider: IdentityProvider = Depends(get_identity_provider),
) -> AuthResponse:
    # Every new account starts on a 7-day trial window, same as /signup-trial -
    # otherwise a direct email/password signup would have no subscription_end
    # at all, which subscription_status() reads as "never expires".
    now = datetime.now(UTC)
    user = User(
        email=body.email,
        display_name=body.display_name,
        role=UserRole.USER.value,
        is_active=True,
        password_hash=hash_password(body.password),
        subscription_package="TRIAL_7D",
        subscription_start=now,
        subscription_end=now + timedelta(days=subscriptions.PACKAGE_DURATION_DAYS["TRIAL_7D"]),
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
        must_change_password=user.must_change_password,
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
        must_change_password=user.must_change_password,
    )


# ---------------------------------------------------------------------------
# Trial signup (password-less): auto-provisions a 7-day trial account with a
# system-generated temp password, emailed to the user. No token is issued
# here - the user logs in with the emailed password via /auth/login, which
# forces them to /auth/set-password on first success (see must_change_password).
# ---------------------------------------------------------------------------


@router.post(
    "/signup-trial", response_model=SignupTrialResponse, status_code=status.HTTP_201_CREATED
)
def signup_trial(
    body: SignupTrialRequest,
    db: Session = Depends(get_db),
    sender: EmailSender = Depends(get_email_sender),
) -> SignupTrialResponse:
    try:
        user, temp_password = subscriptions.create_user_with_temp_password(
            db,
            email=body.email,
            display_name=body.name,
            phone=body.phone,
            package="TRIAL_7D",
        )
    except subscriptions.EmailAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="an account with this email already exists"
        ) from exc

    notifications.send_trial_welcome_email(
        sender, to=user.email, display_name=user.display_name, temp_password=temp_password
    )
    return SignupTrialResponse(email=user.email)


# ---------------------------------------------------------------------------
# Google sign-in - optional, never required. "Continue with Google" on
# signup provisions a trial account the same way /signup-trial does (temp
# password emailed to the Google account's address, must_change_password
# forces a first login by password). Only after that first password login
# clears must_change_password can /auth/login-google be used - this is a
# deliberate email-ownership check, same one the temp-password flow relies on
# elsewhere: Google merely proves "this address exists and is verified",
# not "this person already controls this account".
# ---------------------------------------------------------------------------


@router.post(
    "/signup-google", response_model=SignupTrialResponse, status_code=status.HTTP_201_CREATED
)
def signup_google(
    body: GoogleAuthRequest,
    db: Session = Depends(get_db),
    sender: EmailSender = Depends(get_email_sender),
    settings: Settings = Depends(get_settings),
) -> SignupTrialResponse:
    try:
        identity = verify_google_id_token(
            body.credential, client_id=settings.google_oauth_client_id
        )
    except GoogleTokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    try:
        user, temp_password = subscriptions.create_user_with_temp_password(
            db,
            email=identity.email,
            display_name=identity.name,
            phone=None,
            package="TRIAL_7D",
        )
    except subscriptions.EmailAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="an account with this email already exists"
        ) from exc

    notifications.send_trial_welcome_email(
        sender, to=user.email, display_name=user.display_name, temp_password=temp_password
    )
    return SignupTrialResponse(email=user.email)


@router.post("/login-google", response_model=AuthResponse)
def login_google(
    body: GoogleAuthRequest,
    db: Session = Depends(get_db),
    provider: IdentityProvider = Depends(get_identity_provider),
    settings: Settings = Depends(get_settings),
) -> AuthResponse:
    try:
        identity = verify_google_id_token(
            body.credential, client_id=settings.google_oauth_client_id
        )
    except GoogleTokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    user = db.scalar(select(User).where(User.email == identity.email))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="no account for this Google email - sign up first",
        )
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="account is inactive")
    if user.must_change_password:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "complete your first login with the emailed password " "before using Google sign-in"
            ),
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
        must_change_password=user.must_change_password,
    )


@router.post("/set-password")
def set_password(
    body: SetPasswordRequest,
    db: Session = Depends(get_db),
    claims: Claims = Depends(current_claims),
) -> dict[str, bool]:
    """A valid session token already proves possession of the current
    (possibly temp) password - no re-entry required."""
    user = db.get(User, uuid.UUID(claims.subject))
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")

    user.password_hash = hash_password(body.new_password)
    user.must_change_password = False
    db.commit()
    return {"ok": True}


@router.post("/forgot-password", response_model=ForgotPasswordResponse)
def forgot_password(
    body: ForgotPasswordRequest,
    db: Session = Depends(get_db),
    sender: EmailSender = Depends(get_email_sender),
) -> ForgotPasswordResponse:
    # Always the same generic response - no email enumeration.
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if user is not None and user.is_active:
        raw_token = secrets.token_urlsafe(32)
        token = PasswordResetToken(
            user_id=user.id,
            token_hash=hashlib.sha256(raw_token.encode("utf-8")).hexdigest(),
            expires_at=datetime.now(UTC) + _RESET_TOKEN_TTL,
        )
        db.add(token)
        db.commit()

        reset_url = f"{get_settings().frontend_base_url}/reset-password?token={raw_token}"
        notifications.send_password_reset_email(sender, to=user.email, reset_url=reset_url)

    return ForgotPasswordResponse()


@router.post("/reset-password")
def reset_password(body: ResetPasswordRequest, db: Session = Depends(get_db)) -> dict[str, bool]:
    # A token here is either a self-service forgot-password token or an
    # admin-invite token (see AdminInvite's docstring) - same URL, same
    # hash/expiry/used_at shape, so one lookup handles both.
    token_hash = hashlib.sha256(body.token.encode("utf-8")).hexdigest()
    now = datetime.now(UTC)
    token: PasswordResetToken | AdminInvite | None = db.scalar(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash)
    )
    if token is None:
        token = db.scalar(select(AdminInvite).where(AdminInvite.token_hash == token_hash))
    if token is None or token.used_at is not None or token.expires_at < now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="invalid or expired reset token"
        )

    user = db.get(User, token.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")

    user.password_hash = hash_password(body.new_password)
    user.must_change_password = False
    token.used_at = now
    db.commit()
    return {"ok": True}
