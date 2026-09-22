"""BestEffortEmailSender - keeps a dead mailbox from failing a request.

Every send happens *after* its database work has been committed (account
created, payment approved, subscription extended), so letting an SMTP
outage raise would return a 500 for work that actually succeeded, and the
caller would reasonably retry it. The delivery failure is logged at ERROR
instead - never the body, which can carry a temp password or a reset link.
"""

from __future__ import annotations

import logging

from app.email.base import EmailError, EmailSender

log = logging.getLogger("api.email")


class BestEffortEmailSender(EmailSender):
    def __init__(self, inner: EmailSender) -> None:
        self._inner = inner

    def send(self, *, to: str, subject: str, body_text: str, body_html: str | None = None) -> None:
        try:
            self._inner.send(to=to, subject=subject, body_text=body_text, body_html=body_html)
        except EmailError:
            log.exception("email delivery failed: to=%s subject=%r", to, subject)
