from __future__ import annotations

from functools import lru_cache

from app.config import get_settings
from app.email.base import EmailError, EmailSender
from app.email.best_effort import BestEffortEmailSender
from app.email.brevo import BrevoEmailSender
from app.email.mock import MockEmailSender
from app.email.smtp import SmtpEmailSender

__all__ = [
    "BestEffortEmailSender",
    "BrevoEmailSender",
    "EmailError",
    "EmailSender",
    "MockEmailSender",
    "SmtpEmailSender",
    "get_email_sender",
]


@lru_cache
def get_email_sender() -> EmailSender:
    s = get_settings()
    if s.email_backend == "brevo":
        return BestEffortEmailSender(
            BrevoEmailSender(
                api_key=s.brevo_api_key.get_secret_value(),
                from_name=s.smtp_from_name,
                from_address=s.smtp_from_address,
            )
        )
    if s.email_backend == "smtp":
        return BestEffortEmailSender(
            SmtpEmailSender(
                host=s.smtp_host,
                port=s.smtp_port,
                username=s.smtp_username,
                password=s.smtp_password.get_secret_value(),
                from_name=s.smtp_from_name,
                from_address=s.smtp_from_address,
            )
        )
    return MockEmailSender()
