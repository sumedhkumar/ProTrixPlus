"""Account-level subscription window: package durations, provisioning a new
user with a system-generated temp password, renewal-window math, and the
status shape the dashboard reads.

Distinct from ``services/marketplace.py``'s per-*strategy* entitlements -
this is the account-wide "can this client use the platform at all" window.
"""

from __future__ import annotations

import math
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from protrix_contracts.db.models import User
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import hash_password

# Deliberately code-level constants, not an admin-editable DB table - a v1
# scope limit. Extending this to a real pricing/package table is a
# reasonable follow-up, not required for the manual-review MVP flow.
PACKAGE_DURATION_DAYS: dict[str, int] = {
    "TRIAL_7D": 7,
    "PLAN_3M": 90,
    "PLAN_6M": 180,
    "PLAN_12M": 365,
}
GRACE_PERIOD = timedelta(days=1)


class EmailAlreadyExistsError(Exception):
    pass


def generate_temp_password() -> str:
    """High-entropy, URL-safe - short enough to type from an email, long
    enough that it isn't the weak link (the forced first-login reset is)."""
    return secrets.token_urlsafe(9)


def create_user_with_temp_password(
    session: Session,
    *,
    email: str,
    display_name: str,
    phone: str,
    package: str,
    start: datetime | None = None,
) -> tuple[User, str]:
    """Provision a new account with a random password the caller must email
    to the user, and ``must_change_password=True`` so they're forced to pick
    their own on first login. Used by both trial signup and an approved
    payment submission from an applicant with no existing account."""
    now = datetime.now(UTC)
    period_start = start or now
    temp_password = generate_temp_password()

    user = User(
        email=email,
        display_name=display_name,
        role="USER",
        is_active=True,
        password_hash=hash_password(temp_password),
        phone=phone,
        must_change_password=True,
        subscription_package=package,
        subscription_start=period_start,
        subscription_end=period_start + timedelta(days=PACKAGE_DURATION_DAYS[package]),
    )
    session.add(user)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise EmailAlreadyExistsError(f"an account with email {email!r} already exists") from exc
    session.refresh(user)
    return user, temp_password


def compute_renewal_window(
    current_end: datetime | None, now: datetime, package: str
) -> tuple[datetime, datetime]:
    """Stack on top of a still-active subscription; restart from `now`
    (the admin's approval time) if it already lapsed (including grace)."""
    start = current_end if current_end is not None and current_end > now else now
    return start, start + timedelta(days=PACKAGE_DURATION_DAYS[package])


def subscription_status(user: User, now: datetime) -> dict[str, Any]:
    end = user.subscription_end
    if end is None:
        return {
            "package": None,
            "start": None,
            "end": None,
            "days_remaining": None,
            "is_expired": False,
            "in_grace": False,
            "grace_ends_at": None,
            "hard_blocked": False,
        }

    grace_ends_at = end + GRACE_PERIOD
    is_expired = now > end
    in_grace = end < now <= grace_ends_at
    hard_blocked = now > grace_ends_at
    days_remaining = None if is_expired else math.ceil((end - now).total_seconds() / 86400)

    return {
        "package": user.subscription_package,
        "start": user.subscription_start.isoformat() if user.subscription_start else None,
        "end": end.isoformat(),
        "days_remaining": days_remaining,
        "is_expired": is_expired,
        "in_grace": in_grace,
        "grace_ends_at": grace_ends_at.isoformat(),
        "hard_blocked": hard_blocked,
    }
