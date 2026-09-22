"""BrevoEmailSender - transactional mail over Brevo's HTTPS API.

Render blocks outbound traffic to SMTP ports (25, 465, 587) on free web
services, so :class:`~app.email.smtp.SmtpEmailSender` cannot reach Gmail
there - the connection just times out. This backend talks HTTPS on 443
instead, which is never blocked.

Brevo's free tier sends 300 messages/day and verifies a single sender
address by email link, so no custom domain is needed - the sender stays
``PROTRIX_SMTP_FROM_ADDRESS``, which must be the address verified under
Senders in the Brevo dashboard or the API rejects the send.

API reference: https://developers.brevo.com/docs/send-a-transactional-email
"""

from __future__ import annotations

from typing import Any

import httpx

from app.email.base import EmailError, EmailSender

_ENDPOINT = "https://api.brevo.com/v3/smtp/email"
_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0)


class BrevoEmailSender(EmailSender):
    def __init__(self, *, api_key: str, from_name: str, from_address: str) -> None:
        self._api_key = api_key
        self._from_name = from_name
        self._from_address = from_address

    def send(self, *, to: str, subject: str, body_text: str, body_html: str | None = None) -> None:
        payload: dict[str, Any] = {
            "sender": {"name": self._from_name, "email": self._from_address},
            "to": [{"email": to}],
            "subject": subject,
            "textContent": body_text,
        }
        if body_html:
            payload["htmlContent"] = body_html

        try:
            response = httpx.post(
                _ENDPOINT,
                json=payload,
                headers={
                    "api-key": self._api_key,
                    "content-type": "application/json",
                    "accept": "application/json",
                },
                timeout=_TIMEOUT,
            )
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise EmailError(f"failed to send email to {to}: {exc}") from exc

        if response.status_code >= 300:
            # Brevo puts the reason ("sender not valid", quota exceeded, bad
            # key) in the body; it never echoes back the message itself.
            raise EmailError(
                f"failed to send email to {to}: Brevo returned "
                f"{response.status_code}: {response.text[:300]}"
            )
