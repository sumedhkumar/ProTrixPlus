"""MVP control-plane APIs.

These endpoints expose the data that the worker enforces.  They never accept
broker credentials, order tickets, or a user-selected execution transport;
orders still enter only through the authenticated webhook and are scoped by
the server-side assignment/account mapping.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from protrix_contracts.db.models import (
    AccountCategory,
    AccountTransport,
    AssignmentStatus,
    AuditEvent,
    ManagedPosition,
    RentLedgerEntry,
    RentLedgerEntryType,
    RiskProfile,
    Strategy,
    StrategyAssignment,
    Subscription,
    SubscriptionStatus,
    TradingAccount,
    TradingAccountStatus,
    TradingControl,
    User,
    UserRole,
)
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.identity import Claims
from app.security import current_claims, require_role

router = APIRouter(prefix="/api/v1", tags=["mvp"])
admin_router = APIRouter(
    prefix="/api/v1/admin",
    tags=["mvp-admin"],
    dependencies=[Depends(require_role(UserRole.SUPER_ADMIN))],
)


class AssignmentUpdate(BaseModel):
    multiplier: Decimal | None = Field(default=None, gt=0)
    status: AssignmentStatus | None = None


class WalletTopUp(BaseModel):
    user_id: UUID
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=8)
    idempotency_key: str = Field(min_length=8, max_length=256)
    reason: str | None = Field(default=None, max_length=240)


class ControlUpdate(BaseModel):
    admin_suspended: bool | None = None
    risk_blocked: bool | None = None
    kill_switch: bool | None = None


class SubscriptionUpdate(BaseModel):
    plan_code: str = Field(min_length=1, max_length=64)
    status: SubscriptionStatus
    starts_at: datetime
    ends_at: datetime

    @field_validator("starts_at", "ends_at")
    @classmethod
    def _utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("timestamp must include a timezone")
        return value.astimezone(UTC)


class RiskProfileUpdate(BaseModel):
    max_lot: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    max_open_trades: int = Field(gt=0, le=1000)
    max_daily_loss: Decimal = Field(ge=0, max_digits=18, decimal_places=8)
    allowed_symbols: list[str] = Field(min_length=1, max_length=100)

    @field_validator("allowed_symbols")
    @classmethod
    def _symbols(cls, value: list[str]) -> list[str]:
        normalized = sorted({symbol.strip().upper() for symbol in value if symbol.strip()})
        if not normalized or any(len(symbol) > 32 for symbol in normalized):
            raise ValueError("provide non-empty symbols up to 32 characters")
        return normalized


class AccountUpdate(BaseModel):
    provider_name: str = Field(min_length=1, max_length=120)
    server_identifier: str | None = Field(default=None, max_length=160)
    category: AccountCategory
    transport: AccountTransport
    status: TradingAccountStatus
    external_account_ref: str | None = Field(default=None, max_length=160)
    credential_key_ref: str | None = Field(default=None, max_length=160)


def _subject(claims: Claims) -> UUID:
    try:
        return UUID(claims.subject)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid subject"
        ) from exc


def _get_user(db: Session, user_id: UUID) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    return user


def _audit(
    db: Session,
    *,
    event_type: str,
    entity_type: str,
    entity_id: str,
    actor: str,
    data: dict[str, Any],
) -> None:
    db.add(
        AuditEvent(
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            actor=actor,
            data=data,
        )
    )


def _wallet_balance(db: Session, user_id: UUID) -> Decimal:
    value = db.scalar(
        select(func.coalesce(func.sum(RentLedgerEntry.amount), Decimal("0"))).where(
            RentLedgerEntry.user_id == user_id
        )
    )
    return Decimal(value)


def _assignment_view(assignment: StrategyAssignment, strategy: Strategy) -> dict[str, Any]:
    return {
        "id": str(assignment.id),
        "strategy_key": strategy.strategy_key,
        "strategy_version": strategy.strategy_version,
        "master_lot": format(assignment.master_lot, "f"),
        "multiplier": format(assignment.multiplier, "f"),
        "multiplier_min": format(assignment.multiplier_min, "f"),
        "multiplier_max": format(assignment.multiplier_max, "f"),
        "status": assignment.status,
    }


def _account_view(account: TradingAccount | None) -> dict[str, Any] | None:
    if account is None:
        return None
    heartbeat = account.worker_heartbeat_at
    worker_status = "NO_WORKER"
    if heartbeat is not None:
        worker_status = (
            "HEALTHY" if heartbeat >= datetime.now(UTC) - timedelta(seconds=45) else "STALE"
        )
    return {
        "provider_name": account.provider_name,
        "server_identifier": account.server_identifier,
        "category": account.category,
        "transport": account.transport,
        "status": account.status,
        "external_account_ref": account.external_account_ref,
        "credential_key_ref": account.credential_key_ref,
        "worker_adapter": account.worker_adapter,
        "worker_name": account.worker_name,
        "worker_heartbeat_at": heartbeat.isoformat() if heartbeat else None,
        "worker_status": worker_status,
    }


@router.get("/portfolio")
def portfolio(
    db: Session = Depends(get_db), claims: Claims = Depends(current_claims)
) -> dict[str, Any]:
    """Return only the authenticated user's server-side trading state."""
    user_id = _subject(claims)
    user = _get_user(db, user_id)
    account = db.scalar(select(TradingAccount).where(TradingAccount.user_id == user_id))
    subscription = db.scalar(select(Subscription).where(Subscription.user_id == user_id))
    control = db.scalar(select(TradingControl).where(TradingControl.user_id == user_id))
    risk = db.scalar(select(RiskProfile).where(RiskProfile.user_id == user_id))
    assignments = db.execute(
        select(StrategyAssignment, Strategy)
        .join(Strategy, StrategyAssignment.strategy_id == Strategy.id)
        .where(StrategyAssignment.user_id == user_id)
        .order_by(Strategy.strategy_key)
    ).all()
    positions = db.scalars(
        select(ManagedPosition)
        .where(ManagedPosition.user_id == user_id)
        .order_by(ManagedPosition.updated_at.desc())
        .limit(100)
    ).all()
    return {
        "user": {"id": str(user.id), "display_name": user.display_name, "email": user.email},
        "wallet": {"currency": "USD", "balance": format(_wallet_balance(db, user_id), "f")},
        "account": _account_view(account),
        "subscription": None
        if subscription is None
        else {
            "plan_code": subscription.plan_code,
            "status": subscription.status,
            "starts_at": subscription.starts_at.isoformat(),
            "ends_at": subscription.ends_at.isoformat(),
        },
        "controls": None
        if control is None
        else {
            "admin_suspended": control.admin_suspended,
            "risk_blocked": control.risk_blocked,
            "kill_switch": control.kill_switch,
        },
        "risk_profile": None
        if risk is None
        else {
            "max_lot": format(risk.max_lot, "f"),
            "max_open_trades": risk.max_open_trades,
            "max_daily_loss": format(risk.max_daily_loss, "f"),
            "allowed_symbols": risk.allowed_symbols,
        },
        "assignments": [
            _assignment_view(assignment, strategy) for assignment, strategy in assignments
        ],
        "managed_positions": [
            {
                "id": str(position.id),
                "source_position_ref": position.source_position_ref,
                "broker_position_ref": position.broker_position_ref,
                "symbol": position.symbol,
                "side": position.side,
                "initial_volume": format(position.initial_volume, "f"),
                "remaining_volume": format(position.remaining_volume, "f"),
                "status": position.status,
                "updated_at": position.updated_at.isoformat(),
            }
            for position in positions
        ],
    }


@router.patch("/assignments/{assignment_id}")
def update_own_assignment(
    assignment_id: UUID,
    body: AssignmentUpdate,
    db: Session = Depends(get_db),
    claims: Claims = Depends(current_claims),
) -> dict[str, Any]:
    user_id = _subject(claims)
    row = db.execute(
        select(StrategyAssignment, Strategy)
        .join(Strategy, StrategyAssignment.strategy_id == Strategy.id)
        .where(StrategyAssignment.id == assignment_id, StrategyAssignment.user_id == user_id)
    ).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="assignment not found")
    assignment, strategy = row
    if body.multiplier is not None:
        if not assignment.multiplier_min <= body.multiplier <= assignment.multiplier_max:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="multiplier outside assignment bounds",
            )
        assignment.multiplier = body.multiplier
    if body.status is not None:
        assignment.status = body.status.value
    _audit(
        db,
        event_type="assignment.updated",
        entity_type="strategy_assignment",
        entity_id=str(assignment.id),
        actor=claims.subject,
        data={
            "by": "user",
            "multiplier": format(assignment.multiplier, "f"),
            "status": assignment.status,
        },
    )
    return _assignment_view(assignment, strategy)


@admin_router.get("/operations")
def operations(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    """Admin list of all MVP trading controls; never includes credentials."""
    users = db.scalars(select(User).order_by(User.created_at)).all()
    output: list[dict[str, Any]] = []
    for user in users:
        account = db.scalar(select(TradingAccount).where(TradingAccount.user_id == user.id))
        subscription = db.scalar(select(Subscription).where(Subscription.user_id == user.id))
        control = db.scalar(select(TradingControl).where(TradingControl.user_id == user.id))
        risk = db.scalar(select(RiskProfile).where(RiskProfile.user_id == user.id))
        output.append(
            {
                "user_id": str(user.id),
                "email": user.email,
                "display_name": user.display_name,
                "wallet_balance": format(_wallet_balance(db, user.id), "f"),
                "account": _account_view(account),
                "subscription_status": subscription.status if subscription else None,
                "subscription": None
                if subscription is None
                else {
                    "plan_code": subscription.plan_code,
                    "status": subscription.status,
                    "starts_at": subscription.starts_at.isoformat(),
                    "ends_at": subscription.ends_at.isoformat(),
                },
                "controls": None
                if control is None
                else {
                    "admin_suspended": control.admin_suspended,
                    "risk_blocked": control.risk_blocked,
                    "kill_switch": control.kill_switch,
                },
                "risk": None
                if risk is None
                else {
                    "max_lot": format(risk.max_lot, "f"),
                    "max_open_trades": risk.max_open_trades,
                    "max_daily_loss": format(risk.max_daily_loss, "f"),
                    "allowed_symbols": risk.allowed_symbols,
                },
            }
        )
    return output


@admin_router.post("/wallet/top-ups", status_code=status.HTTP_201_CREATED)
def top_up_wallet(
    body: WalletTopUp,
    db: Session = Depends(get_db),
    claims: Claims = Depends(current_claims),
) -> dict[str, Any]:
    _get_user(db, body.user_id)
    existing = db.scalar(
        select(RentLedgerEntry).where(RentLedgerEntry.idempotency_key == body.idempotency_key)
    )
    if existing is not None:
        if (
            existing.user_id == body.user_id
            and existing.entry_type == RentLedgerEntryType.TOP_UP.value
            and existing.amount == body.amount
        ):
            return {
                "entry_id": str(existing.id),
                "balance": format(_wallet_balance(db, body.user_id), "f"),
                "replayed": True,
            }
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="idempotency key already used"
        )
    entry = RentLedgerEntry(
        user_id=body.user_id,
        settlement_id=None,
        entry_type=RentLedgerEntryType.TOP_UP.value,
        amount=body.amount,
        currency="USD",
        idempotency_key=body.idempotency_key,
        reason=body.reason,
        actor=claims.subject,
    )
    db.add(entry)
    db.flush()
    _audit(
        db,
        event_type="wallet.top_up",
        entity_type="rent_ledger_entry",
        entity_id=str(entry.id),
        actor=claims.subject,
        data={"user_id": str(body.user_id), "amount": format(body.amount, "f"), "currency": "USD"},
    )
    return {
        "entry_id": str(entry.id),
        "balance": format(_wallet_balance(db, body.user_id), "f"),
        "replayed": False,
    }


@admin_router.put("/users/{user_id}/controls")
def update_controls(
    user_id: UUID,
    body: ControlUpdate,
    db: Session = Depends(get_db),
    claims: Claims = Depends(current_claims),
) -> dict[str, bool]:
    _get_user(db, user_id)
    control = db.scalar(select(TradingControl).where(TradingControl.user_id == user_id))
    if control is None:
        control = TradingControl(user_id=user_id)
        db.add(control)
    for field in ("admin_suspended", "risk_blocked", "kill_switch"):
        value = getattr(body, field)
        if value is not None:
            setattr(control, field, value)
    db.flush()
    response = {
        field: bool(getattr(control, field))
        for field in ("admin_suspended", "risk_blocked", "kill_switch")
    }
    _audit(
        db,
        event_type="trading_controls.updated",
        entity_type="trading_control",
        entity_id=str(control.id),
        actor=claims.subject,
        data={"user_id": str(user_id), **response},
    )
    return response


@admin_router.put("/users/{user_id}/subscription")
def update_subscription(
    user_id: UUID,
    body: SubscriptionUpdate,
    db: Session = Depends(get_db),
    claims: Claims = Depends(current_claims),
) -> dict[str, Any]:
    _get_user(db, user_id)
    if body.ends_at <= body.starts_at:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="ends_at must be after starts_at",
        )
    subscription = db.scalar(select(Subscription).where(Subscription.user_id == user_id))
    if subscription is None:
        subscription = Subscription(user_id=user_id, **body.model_dump())
        subscription.status = body.status.value
        db.add(subscription)
    else:
        subscription.plan_code = body.plan_code
        subscription.status = body.status.value
        subscription.starts_at = body.starts_at
        subscription.ends_at = body.ends_at
    db.flush()
    response = {
        "plan_code": subscription.plan_code,
        "status": subscription.status,
        "starts_at": subscription.starts_at.isoformat(),
        "ends_at": subscription.ends_at.isoformat(),
    }
    _audit(
        db,
        event_type="subscription.updated",
        entity_type="subscription",
        entity_id=str(subscription.id),
        actor=claims.subject,
        data={"user_id": str(user_id), **response},
    )
    return response


@admin_router.put("/users/{user_id}/risk-profile")
def update_risk_profile(
    user_id: UUID,
    body: RiskProfileUpdate,
    db: Session = Depends(get_db),
    claims: Claims = Depends(current_claims),
) -> dict[str, Any]:
    _get_user(db, user_id)
    risk = db.scalar(select(RiskProfile).where(RiskProfile.user_id == user_id))
    values = body.model_dump()
    if risk is None:
        risk = RiskProfile(user_id=user_id, **values)
        db.add(risk)
    else:
        for field, value in values.items():
            setattr(risk, field, value)
    db.flush()
    response = {
        "max_lot": format(risk.max_lot, "f"),
        "max_open_trades": risk.max_open_trades,
        "max_daily_loss": format(risk.max_daily_loss, "f"),
        "allowed_symbols": risk.allowed_symbols,
    }
    _audit(
        db,
        event_type="risk_profile.updated",
        entity_type="risk_profile",
        entity_id=str(risk.id),
        actor=claims.subject,
        data={"user_id": str(user_id), **response},
    )
    return response


@admin_router.put("/users/{user_id}/account")
def update_account(
    user_id: UUID,
    body: AccountUpdate,
    db: Session = Depends(get_db),
    claims: Claims = Depends(current_claims),
) -> dict[str, Any]:
    _get_user(db, user_id)
    account = db.scalar(select(TradingAccount).where(TradingAccount.user_id == user_id))
    values = body.model_dump(mode="json")
    values["category"] = body.category.value
    values["transport"] = body.transport.value
    values["status"] = body.status.value
    if account is None:
        account = TradingAccount(id=user_id, user_id=user_id, **values)
        db.add(account)
    else:
        for field, value in values.items():
            setattr(account, field, value)
    db.flush()
    response = _account_view(account)
    _audit(
        db,
        event_type="trading_account.updated",
        entity_type="trading_account",
        entity_id=str(account.id),
        actor=claims.subject,
        data={
            "user_id": str(user_id),
            "provider_name": account.provider_name,
            "category": account.category,
            "transport": account.transport,
            "status": account.status,
        },
    )
    return response


@admin_router.patch("/assignments/{assignment_id}")
def update_assignment_as_admin(
    assignment_id: UUID,
    body: AssignmentUpdate,
    db: Session = Depends(get_db),
    claims: Claims = Depends(current_claims),
) -> dict[str, Any]:
    row = db.execute(
        select(StrategyAssignment, Strategy)
        .join(Strategy, StrategyAssignment.strategy_id == Strategy.id)
        .where(StrategyAssignment.id == assignment_id)
    ).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="assignment not found")
    assignment, strategy = row
    if body.multiplier is not None:
        if not assignment.multiplier_min <= body.multiplier <= assignment.multiplier_max:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="multiplier outside assignment bounds",
            )
        assignment.multiplier = body.multiplier
    if body.status is not None:
        assignment.status = body.status.value
    db.flush()
    response = _assignment_view(assignment, strategy)
    _audit(
        db,
        event_type="assignment.admin_updated",
        entity_type="strategy_assignment",
        entity_id=str(assignment.id),
        actor=claims.subject,
        data={
            "user_id": str(assignment.user_id),
            "multiplier": response["multiplier"],
            "status": response["status"],
        },
    )
    return response
