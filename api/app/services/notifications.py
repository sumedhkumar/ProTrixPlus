"""Subject/body builders for every outbound email this feature sends. Thin
on purpose - plain text (+ a matching simple HTML body), no template engine.
"""

from __future__ import annotations

from datetime import datetime

from protrix_contracts.db.models import PaymentSubmission

from app.email import EmailSender

_PACKAGE_LABEL = {
    "TRIAL_7D": "7-Day Free Trial",
    "PLAN_3M": "3-Month Plan",
    "PLAN_6M": "6-Month Plan",
    "PLAN_12M": "1-Year Plan",
}


def _label(package: str) -> str:
    return _PACKAGE_LABEL.get(package, package)


def send_trial_welcome_email(
    sender: EmailSender, *, to: str, display_name: str, temp_password: str
) -> None:
    subject = "Welcome to ProTrixPlus - your login details"
    body = (
        f"Hi {display_name},\n\n"
        "Your ProTrixPlus 7-day free trial account is ready.\n\n"
        f"Email: {to}\n"
        f"Temporary password: {temp_password}\n\n"
        "Log in at your convenience - you'll be asked to set your own "
        "password on first login.\n\n- ProTrixPlus"
    )
    sender.send(to=to, subject=subject, body_text=body)


def send_payment_admin_notification(
    sender: EmailSender, *, admin_to: str, submission: PaymentSubmission
) -> None:
    if not admin_to:
        return
    subject = f"[ProTrixPlus] Payment review needed - {_label(submission.package)}"
    body = (
        f"New payment submission awaiting review:\n\n"
        f"Name: {submission.name}\n"
        f"Email: {submission.email}\n"
        f"Phone: {submission.phone}\n"
        f"Package: {_label(submission.package)}\n"
        f"UTR / transaction reference: {submission.utr_reference}\n"
        f"Existing account: {'yes' if submission.user_id else 'no'}\n\n"
        "Review it in the admin panel under Payment Review."
    )
    sender.send(to=admin_to, subject=subject, body_text=body)


def send_payment_submitted_email(
    sender: EmailSender, *, to: str, display_name: str, package: str, utr_reference: str
) -> None:
    subject = f"ProTrixPlus - payment received for {_label(package)}"
    body = (
        f"Hi {display_name},\n\n"
        f"We've received your payment submission for the {_label(package)} "
        f"(reference: {utr_reference}).\n\n"
        "Our team will review it shortly and you'll get a confirmation email "
        "once it's approved.\n\n- ProTrixPlus"
    )
    sender.send(to=to, subject=subject, body_text=body)


def send_payment_approved_new_account_email(
    sender: EmailSender, *, to: str, display_name: str, temp_password: str, package: str
) -> None:
    subject = "ProTrixPlus payment confirmed - your login details"
    body = (
        f"Hi {display_name},\n\n"
        f"Your payment for the {_label(package)} has been confirmed and your "
        "account is ready.\n\n"
        f"Email: {to}\n"
        f"Temporary password: {temp_password}\n\n"
        "Log in at your convenience - you'll be asked to set your own "
        "password on first login.\n\n- ProTrixPlus"
    )
    sender.send(to=to, subject=subject, body_text=body)


def send_subscription_renewed_email(
    sender: EmailSender, *, to: str, display_name: str, package: str, new_end: datetime
) -> None:
    subject = "ProTrixPlus subscription renewed"
    body = (
        f"Hi {display_name},\n\n"
        f"Your payment was confirmed and your {_label(package)} is now active "
        f"through {new_end:%Y-%m-%d}.\n\n- ProTrixPlus"
    )
    sender.send(to=to, subject=subject, body_text=body)


def send_payment_rejected_email(
    sender: EmailSender, *, to: str, display_name: str, reason: str | None
) -> None:
    subject = "ProTrixPlus payment submission could not be confirmed"
    body = (
        f"Hi {display_name},\n\n"
        "We couldn't confirm your recent payment submission"
        + (f": {reason}" if reason else ".")
        + "\n\nPlease double-check your transaction reference and submit again, "
        "or contact support if you believe this is a mistake.\n\n- ProTrixPlus"
    )
    sender.send(to=to, subject=subject, body_text=body)


def send_password_reset_email(sender: EmailSender, *, to: str, reset_url: str) -> None:
    subject = "Reset your ProTrixPlus password"
    body = (
        "We received a request to reset your ProTrixPlus password.\n\n"
        f"Reset it here (valid for 1 hour): {reset_url}\n\n"
        "If you didn't request this, you can safely ignore this email.\n\n"
        "- ProTrixPlus"
    )
    sender.send(to=to, subject=subject, body_text=body)


def send_admin_invite_email(
    sender: EmailSender, *, to: str, display_name: str, invite_url: str, role_labels: list[str]
) -> None:
    roles = ", ".join(role_labels)
    subject = "You've been invited to the ProTrixPlus admin team"
    body = (
        f"Hi {display_name},\n\n"
        f"You've been added to the ProTrixPlus admin panel with the following "
        f"role(s): {roles}.\n\n"
        f"Set your password here (valid for 7 days): {invite_url}\n\n"
        "If you weren't expecting this, you can safely ignore this email.\n\n"
        "- ProTrixPlus"
    )
    sender.send(to=to, subject=subject, body_text=body)


def send_admin_roles_updated_email(
    sender: EmailSender, *, to: str, display_name: str, role_labels: list[str]
) -> None:
    roles = ", ".join(role_labels)
    subject = "Your ProTrixPlus admin roles were updated"
    body = (
        f"Hi {display_name},\n\n"
        f"Your ProTrixPlus admin roles are now: {roles}.\n\n"
        "Log in to the admin panel to see what's changed.\n\n- ProTrixPlus"
    )
    sender.send(to=to, subject=subject, body_text=body)
