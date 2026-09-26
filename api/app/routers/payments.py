"""Payment-proof (UTR/transaction reference) submission for paid
subscription packages - public (anonymous applicant) and authenticated
(existing user renewing) variants. See services/payments.py.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from protrix_contracts.db.models import PaymentSubmission
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.email import EmailSender, get_email_sender
from app.identity import Claims
from app.security import current_claims
from app.services import notifications, payments

router = APIRouter(prefix="/api/v1", tags=["payments"])


class PaymentSubmitRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=320)
    phone: str = Field(min_length=1, max_length=32)
    package: str
    utr_reference: str = Field(min_length=1, max_length=64)


class MePaymentSubmitRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    phone: str = Field(min_length=1, max_length=32)
    package: str
    utr_reference: str = Field(min_length=1, max_length=64)


@router.get("/payments/instructions")
def payment_instructions() -> dict[str, str | None]:
    """Manual-payment (bank/UPI) details to show before a UTR submission.
    Public, read-only. Any field left unset in Settings comes back null -
    the frontend renders a "to be added" placeholder for those."""
    s = get_settings()
    return {
        "bank_account_name": s.payment_bank_account_name or None,
        "bank_account_number": s.payment_bank_account_number or None,
        "bank_ifsc": s.payment_bank_ifsc or None,
        "bank_name": s.payment_bank_name or None,
        "upi_id": s.payment_upi_id or None,
        "qr_code_url": s.payment_qr_code_url or None,
    }


@router.post("/payments/submit", status_code=status.HTTP_201_CREATED)
def submit_payment(
    body: PaymentSubmitRequest,
    db: Session = Depends(get_db),
    sender: EmailSender = Depends(get_email_sender),
) -> dict[str, Any]:
    try:
        submission = payments.submit_payment_proof(
            db,
            name=body.name,
            email=body.email.lower(),
            phone=body.phone,
            package=body.package,
            utr_reference=body.utr_reference,
            user_id=None,
        )
    except payments.ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    _notify_admin(sender, submission)
    _notify_customer(sender, submission)
    return {"id": str(submission.id), "status": submission.status}


@router.post("/me/payments/submit", status_code=status.HTTP_201_CREATED)
def submit_my_payment(
    body: MePaymentSubmitRequest,
    db: Session = Depends(get_db),
    claims: Claims = Depends(current_claims),
    sender: EmailSender = Depends(get_email_sender),
) -> dict[str, Any]:
    try:
        submission = payments.submit_payment_proof(
            db,
            name=body.name,
            email=claims.email,
            phone=body.phone,
            package=body.package,
            utr_reference=body.utr_reference,
            user_id=uuid.UUID(claims.subject),
        )
    except payments.ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    _notify_admin(sender, submission)
    _notify_customer(sender, submission)
    return {"id": str(submission.id), "status": submission.status}


def _notify_admin(sender: EmailSender, submission: PaymentSubmission) -> None:
    notifications.send_payment_admin_notification(
        sender, admin_to=get_settings().admin_notify_email, submission=submission
    )


def _notify_customer(sender: EmailSender, submission: PaymentSubmission) -> None:
    notifications.send_payment_submitted_email(
        sender,
        to=submission.email,
        display_name=submission.name,
        package=submission.package,
        utr_reference=submission.utr_reference,
    )
