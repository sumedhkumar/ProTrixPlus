"""Real entitlement gating - PRD acceptance: "An expired/non-entitled client
does not receive a trade." Pure unit tests, no DB needed."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from protrix_contracts.db.models import PaymentStatus, StrategyAssignment, User

from app.eligibility import Eligibility, evaluate

NOW = datetime(2026, 9, 17, 12, 0, 0, tzinfo=UTC)


def _user() -> User:
    return User(email="u@example.test", display_name="U", role="USER")


def _assignment(**overrides) -> StrategyAssignment:
    defaults = dict(
        master_lot=Decimal("1.00"),
        multiplier=Decimal("1.0000"),
        multiplier_min=Decimal("0.5000"),
        multiplier_max=Decimal("2.0000"),
        status="ACTIVE",
        payment_status=PaymentStatus.GRANTED.value,
        expires_at=None,
    )
    defaults.update(overrides)
    return StrategyAssignment(**defaults)


def test_granted_no_expiry_is_active() -> None:
    decision = evaluate(_user(), _assignment(), now=NOW)
    assert decision.status is Eligibility.ACTIVE


def test_granted_future_expiry_is_active() -> None:
    a = _assignment(expires_at=NOW + timedelta(days=1))
    assert evaluate(_user(), a, now=NOW).status is Eligibility.ACTIVE


def test_granted_past_expiry_is_suppressed() -> None:
    a = _assignment(expires_at=NOW - timedelta(seconds=1))
    decision = evaluate(_user(), a, now=NOW)
    assert decision.status is Eligibility.SUPPRESSED
    assert decision.reason == "entitlement-expired"


def test_expiry_exactly_now_is_suppressed() -> None:
    """<=, not <: an entitlement expiring at this exact instant is expired."""
    a = _assignment(expires_at=NOW)
    assert evaluate(_user(), a, now=NOW).status is Eligibility.SUPPRESSED


def test_revoked_is_suppressed_even_without_expiry() -> None:
    a = _assignment(payment_status=PaymentStatus.REVOKED.value, expires_at=None)
    decision = evaluate(_user(), a, now=NOW)
    assert decision.status is Eligibility.SUPPRESSED
    assert decision.reason == "entitlement-revoked"


def test_revoked_checked_before_expiry() -> None:
    """Revoked + not-yet-expired -> still suppressed for the revoked reason."""
    a = _assignment(payment_status=PaymentStatus.REVOKED.value, expires_at=NOW + timedelta(days=30))
    decision = evaluate(_user(), a, now=NOW)
    assert decision.status is Eligibility.SUPPRESSED
    assert decision.reason == "entitlement-revoked"
