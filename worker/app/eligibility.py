"""Backend-authoritative entry eligibility and pre-dispatch risk checks."""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from protrix_contracts.db.models import (
    AccountTransport,
    EnrollmentAccount,
    EnrollmentStatus,
    EscrowLedgerEntry,
    ManagedPosition,
    ManagedPositionStatus,
    RentLedgerEntry,
    RiskProfile,
    StrategyAssignment,
    StrategyEnrollment,
    StrategyPurchase,
    Subscription,
    SubscriptionStatus,
    TradingAccount,
    TradingAccountStatus,
    TradingControl,
    User,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session


class Eligibility(str, enum.Enum):
    ACTIVE = "ACTIVE"
    RENT_EXHAUSTED = "RENT_EXHAUSTED"
    ADMIN_SUSPENDED = "ADMIN_SUSPENDED"
    MT5_DISCONNECTED = "MT5_DISCONNECTED"
    SUBSCRIPTION_EXPIRED = "SUBSCRIPTION_EXPIRED"
    RISK_BLOCKED = "RISK_BLOCKED"


_PRECEDENCE = (
    Eligibility.ADMIN_SUSPENDED,
    Eligibility.RISK_BLOCKED,
    Eligibility.SUBSCRIPTION_EXPIRED,
    Eligibility.RENT_EXHAUSTED,
    Eligibility.MT5_DISCONNECTED,
)


@dataclass(frozen=True)
class EligibilityDecision:
    status: Eligibility
    reasons: tuple[Eligibility, ...]

    @property
    def reason(self) -> str:
        return ",".join(reason.value for reason in self.reasons) or Eligibility.ACTIVE.value


def evaluate(session: Session, user: User, assignment: StrategyAssignment) -> EligibilityDecision:  # noqa: ARG001
    """Return all active blocks plus a deterministic display state."""
    now = datetime.now(UTC)
    reasons: set[Eligibility] = set()
    control = session.scalar(select(TradingControl).where(TradingControl.user_id == user.id))

    if not user.is_active or (control and (control.admin_suspended or control.kill_switch)):
        reasons.add(Eligibility.ADMIN_SUSPENDED)
    if control and control.risk_blocked:
        reasons.add(Eligibility.RISK_BLOCKED)

    # Marketplace enrollments override the legacy per-user account/subscription
    # path. This is how two purchased strategies for one user stay isolated.
    enrollment = session.scalar(
        select(StrategyEnrollment).where(
            StrategyEnrollment.user_id == user.id,
            StrategyEnrollment.strategy_id == assignment.strategy_id,
        )
    )
    if enrollment is not None:
        enrollment_account = session.scalar(
            select(EnrollmentAccount).where(EnrollmentAccount.enrollment_id == enrollment.id)
        )
        access_end = session.scalar(
            select(func.max(StrategyPurchase.ends_at)).where(
                StrategyPurchase.enrollment_id == enrollment.id,
                StrategyPurchase.status == "PAID",
            )
        )
        balance = session.scalar(
            select(func.coalesce(func.sum(EscrowLedgerEntry.amount), Decimal("0"))).where(
                EscrowLedgerEntry.enrollment_id == enrollment.id
            )
        )
        if (
            enrollment.status != EnrollmentStatus.ACTIVE.value
            or enrollment_account is None
            or enrollment_account.status != TradingAccountStatus.ACTIVE.value
        ):
            reasons.add(Eligibility.MT5_DISCONNECTED)
        if (
            enrollment_account is not None
            and enrollment_account.transport == AccountTransport.METAAPI.value
        ):
            # Marketplace MetaApi routing is deliberately unavailable until a
            # real adapter and vault integration are installed.
            reasons.add(Eligibility.MT5_DISCONNECTED)
        # A native account is deliberately fail-closed until its dedicated
        # account-scoped worker has reported in.  This prevents a newly saved
        # strategy credential from being executed by the legacy, user-wide
        # native MT5 worker.
        if (
            enrollment_account is not None
            and enrollment_account.transport == AccountTransport.NATIVE_MT5.value
        ):
            heartbeat_is_fresh = (
                enrollment_account.worker_heartbeat_at is not None
                and (now - enrollment_account.worker_heartbeat_at).total_seconds() <= 90
            )
            if enrollment_account.worker_adapter != "mt5" or not heartbeat_is_fresh:
                reasons.add(Eligibility.MT5_DISCONNECTED)
        if access_end is None or access_end <= now:
            reasons.add(Eligibility.SUBSCRIPTION_EXPIRED)
        balance_value = balance if balance is not None else Decimal("0")
        if Decimal(balance_value) < Decimal(enrollment.minimum_wallet_usd):
            reasons.add(Eligibility.RENT_EXHAUSTED)
    else:
        legacy_account = session.scalar(
            select(TradingAccount).where(TradingAccount.user_id == user.id)
        )
        subscription = session.scalar(select(Subscription).where(Subscription.user_id == user.id))
        if legacy_account is None or legacy_account.status != TradingAccountStatus.ACTIVE.value:
            reasons.add(Eligibility.MT5_DISCONNECTED)
        if (
            subscription is None
            or subscription.status != SubscriptionStatus.ACTIVE.value
            or subscription.ends_at <= now
        ):
            reasons.add(Eligibility.SUBSCRIPTION_EXPIRED)
        balance = session.scalar(
            select(func.coalesce(func.sum(RentLedgerEntry.amount), Decimal("0"))).where(
                RentLedgerEntry.user_id == user.id
            )
        )
        balance_value = balance if balance is not None else Decimal("0")
        if Decimal(balance_value) <= 0:
            reasons.add(Eligibility.RENT_EXHAUSTED)

    ordered = tuple(reason for reason in _PRECEDENCE if reason in reasons)
    return EligibilityDecision(
        status=ordered[0] if ordered else Eligibility.ACTIVE, reasons=ordered
    )


def entry_risk_reasons(
    session: Session, *, user_id: object, symbol: str, volume: Decimal
) -> tuple[str, ...]:
    """Return machine-readable rejection reasons for an otherwise eligible entry."""
    profile = session.scalar(select(RiskProfile).where(RiskProfile.user_id == user_id))
    if profile is None:
        return ("RISK_PROFILE_MISSING",)
    reasons: list[str] = []
    if symbol not in profile.allowed_symbols:
        reasons.append("SYMBOL_NOT_ALLOWED")
    if volume > Decimal(profile.max_lot):
        reasons.append("MAX_LOT_EXCEEDED")
    open_count = session.scalar(
        select(func.count())
        .select_from(ManagedPosition)
        .where(
            ManagedPosition.user_id == user_id,
            ManagedPosition.status == ManagedPositionStatus.OPEN.value,
        )
    )
    if int(open_count or 0) >= profile.max_open_trades:
        reasons.append("MAX_OPEN_TRADES_EXCEEDED")
    return tuple(reasons)
