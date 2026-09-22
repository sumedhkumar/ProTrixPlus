"""EmailSender interface.

Outbound mail for trial-signup temp passwords, payment-submission admin
notifications, and forgot-password reset links. A future real implementation
swaps in behind the same Protocol - nothing outside this package changes.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


class EmailError(Exception):
    """Raised when a message could not be sent."""


@runtime_checkable
class EmailSender(Protocol):
    def send(
        self, *, to: str, subject: str, body_text: str, body_html: str | None = None
    ) -> None: ...
