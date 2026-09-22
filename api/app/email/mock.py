"""MockEmailSender - logs to/subject only, never the body. Local/CI default.

The body can carry a temp password or a password-reset link, so it is
deliberately never logged - only appended to ``self.sent`` for tests to
assert on directly.
"""

from __future__ import annotations

import logging

from app.email.base import EmailSender

log = logging.getLogger("api.email")


class MockEmailSender(EmailSender):
    def __init__(self) -> None:
        self.sent: list[dict[str, str | None]] = []

    def send(self, *, to: str, subject: str, body_text: str, body_html: str | None = None) -> None:
        log.info("mock email: to=%s subject=%r", to, subject)
        self.sent.append(
            {"to": to, "subject": subject, "body_text": body_text, "body_html": body_html}
        )
