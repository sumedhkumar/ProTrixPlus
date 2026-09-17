"""Real entitlement gating (PRD 5.3, 5.5, 5.8).

Replaces the S0 placeholder that always returned ACTIVE. This is the check
that makes two PRD MVP acceptance criteria true:

* "An expired/non-entitled client does not receive a trade."
* Combined with the strategy ON/OFF check in ``fanout.py``: "Turning strategy
  OFF prevents a subsequent signal from opening a new trade."

``AssignmentStatus`` (ACTIVE/PAUSED) is the admin's coarse per-client
enable/disable switch, already filtered before this runs. This module checks
the finer-grained entitlement: payment_status and expiry.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import UTC, datetime

from protrix_contracts.db.models import PaymentStatus, StrategyAssignment, User


class Eligibility(str, enum.Enum):
    ACTIVE = "ACTIVE"
    SUPPRESSED = "SUPPRESSED"


@dataclass(frozen=True)
class EligibilityDecision:
    status: Eligibility
    reason: str


def evaluate(
    user: User,  # noqa: ARG001 - kept for interface stability / future per-user gates
    assignment: StrategyAssignment,
    *,
    now: datetime | None = None,
) -> EligibilityDecision:
    now = now or datetime.now(UTC)

    if assignment.payment_status != PaymentStatus.GRANTED.value:
        return EligibilityDecision(status=Eligibility.SUPPRESSED, reason="entitlement-revoked")

    if assignment.expires_at is not None and assignment.expires_at <= now:
        return EligibilityDecision(status=Eligibility.SUPPRESSED, reason="entitlement-expired")

    return EligibilityDecision(status=Eligibility.ACTIVE, reason="entitled")
