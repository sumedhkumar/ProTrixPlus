"""Manual payment-proof (UTR/transaction reference) review, for paid
SubscriptionPackages - there is no payment gateway in this MVP (see
docs/FULL-BUILD-PLAN.md decision #4, extended here from per-strategy
entitlements to account-level subscriptions).

Pure DB here, same separation as ``services/marketplace.py``: callers
(routers) decide which notification email to send based on the returned
result, this module never sends mail itself.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from protrix_contracts.db.models import PaymentSubmission, User
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.services import subscriptions

PAID_PACKAGES = ("PLAN_3M", "PLAN_6M", "PLAN_12M")


class NotFoundError(Exception):
    pass


class ValidationError(Exception):
    pass


def _submission_dict(s: PaymentSubmission) -> dict[str, Any]:
    return {
        "id": str(s.id),
        "user_id": str(s.user_id) if s.user_id else None,
        "name": s.name,
        "email": s.email,
        "phone": s.phone,
        "package": s.package,
        "utr_reference": s.utr_reference,
        "status": s.status,
        "submitted_at": s.submitted_at.isoformat(),
        "reviewed_at": s.reviewed_at.isoformat() if s.reviewed_at else None,
        "reviewed_by": str(s.reviewed_by) if s.reviewed_by else None,
        "rejection_reason": s.rejection_reason,
    }


def submit_payment_proof(
    session: Session,
    *,
    name: str,
    email: str,
    phone: str,
    package: str,
    utr_reference: str,
    user_id: uuid.UUID | None,
) -> PaymentSubmission:
    if package not in PAID_PACKAGES:
        raise ValidationError(f"package must be one of {PAID_PACKAGES}")

    submission = PaymentSubmission(
        user_id=user_id,
        name=name,
        email=email.lower(),
        phone=phone,
        package=package,
        utr_reference=utr_reference,
        status="PENDING",
    )
    session.add(submission)
    session.commit()
    session.refresh(submission)
    return submission


def admin_list_payment_submissions(
    session: Session, *, status: str | None = None
) -> list[dict[str, Any]]:
    stmt = select(PaymentSubmission).order_by(PaymentSubmission.submitted_at.desc())
    if status:
        stmt = stmt.where(PaymentSubmission.status == status)
    return [_submission_dict(s) for s in session.scalars(stmt).all()]


def admin_approve_payment_submission(
    session: Session, *, submission_id: str, reviewer_subject: str
) -> dict[str, Any]:
    submission = session.get(PaymentSubmission, uuid.UUID(submission_id))
    if submission is None:
        raise NotFoundError(f"payment submission {submission_id} not found")
    if submission.status != "PENDING":
        raise ValidationError(f"submission {submission_id} was already reviewed")

    now = datetime.now(UTC)
    result: dict[str, Any] = {"created_new_account": False, "temp_password": None}

    if submission.user_id is not None:
        existing_user = session.get(User, submission.user_id)
        if existing_user is None:
            raise NotFoundError(f"user {submission.user_id} not found")
    else:
        # Submission wasn't linked to an account at intake, but the email may
        # already belong to one (e.g. a prior trial/Google signup) - treat
        # that as a renewal instead of failing on the email unique constraint.
        existing_user = session.scalar(select(User).where(User.email == submission.email.lower()))

    if existing_user is not None:
        user = existing_user
        start, end = subscriptions.compute_renewal_window(
            user.subscription_end, now, submission.package
        )
        user.subscription_package = submission.package
        user.subscription_start = start
        user.subscription_end = end
        submission.user_id = user.id
    else:
        user, temp_password = subscriptions.create_user_with_temp_password(
            session,
            email=submission.email,
            display_name=submission.name,
            phone=submission.phone,
            package=submission.package,
        )
        submission.user_id = user.id
        result["created_new_account"] = True
        result["temp_password"] = temp_password

    submission.status = "APPROVED"
    submission.reviewed_at = now
    submission.reviewed_by = uuid.UUID(reviewer_subject)
    session.commit()
    session.refresh(user)
    session.refresh(submission)

    result["user"] = user
    result["submission"] = _submission_dict(submission)
    return result


def admin_reject_payment_submission(
    session: Session, *, submission_id: str, reviewer_subject: str, reason: str | None
) -> dict[str, Any]:
    submission = session.get(PaymentSubmission, uuid.UUID(submission_id))
    if submission is None:
        raise NotFoundError(f"payment submission {submission_id} not found")
    if submission.status != "PENDING":
        raise ValidationError(f"submission {submission_id} was already reviewed")

    submission.status = "REJECTED"
    submission.reviewed_at = datetime.now(UTC)
    submission.reviewed_by = uuid.UUID(reviewer_subject)
    submission.rejection_reason = reason
    session.commit()
    session.refresh(submission)
    return _submission_dict(submission)
