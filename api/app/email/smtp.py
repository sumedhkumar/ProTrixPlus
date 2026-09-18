"""SmtpEmailSender - real SMTP delivery (Gmail by default).

Gmail requires an *App Password* (2FA must be enabled on the sending
account), not the account's normal login password - see
https://myaccount.google.com/apppasswords.
"""

from __future__ import annotations

import smtplib
from email.message import EmailMessage

from app.email.base import EmailError, EmailSender


class SmtpEmailSender(EmailSender):
    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        from_name: str,
        from_address: str,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._from_name = from_name
        self._from_address = from_address

    def send(self, *, to: str, subject: str, body_text: str, body_html: str | None = None) -> None:
        msg = EmailMessage()
        msg["From"] = f"{self._from_name} <{self._from_address}>"
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body_text)
        if body_html:
            msg.add_alternative(body_html, subtype="html")

        try:
            with smtplib.SMTP(self._host, self._port, timeout=10) as smtp:
                smtp.starttls()
                smtp.login(self._username, self._password)
                smtp.send_message(msg)
        except (smtplib.SMTPException, OSError) as exc:
            raise EmailError(f"failed to send email to {to}: {exc}") from exc
