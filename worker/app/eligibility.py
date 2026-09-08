"""Placeholder eligibility check.

S0 always returns ACTIVE. The seam exists so a later step can plug in real
gating (funding, drawdown, kill-switch, schedule) without touching fan-out.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass

from protrix_contracts.db.models import StrategyAssignment, User


class Eligibility(str, enum.Enum):
    ACTIVE = "ACTIVE"
    SUPPRESSED = "SUPPRESSED"


@dataclass(frozen=True)
class EligibilityDecision:
    status: Eligibility
    reason: str


def evaluate(user: User, assignment: StrategyAssignment) -> EligibilityDecision:  # noqa: ARG001
    # Placeholder: everyone active for now.
    return EligibilityDecision(status=Eligibility.ACTIVE, reason="s0-placeholder-always-active")
