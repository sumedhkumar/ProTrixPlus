"""Marketplace, escrow, payment, and per-strategy account APIs."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from functools import lru_cache
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from protrix_contracts.db.models import (
    AccountCategory,
    AccountTransport,
    AuditEvent,
    EnrollmentAccount,
    EnrollmentStatus,
    EscrowLedgerEntry,
    PaymentEvent,
    PaymentOrder,
    PaymentPurpose,
    PaymentStatus,
    PurchaseSource,
    Strategy,
    StrategyAssignment,
    StrategyEnrollment,
    StrategyOffer,
    StrategyPurchase,
    StrategySettlement,
    TradingAccountStatus,
    User,
    UserRole,
)
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.identity import Claims
from app.payments import RazorpayError, RazorpayGateway, usd_to_subunits
from app.security import current_claims, require_role
from app.vault import MockCredentialVault, VaultError

router = APIRouter(prefix="/api/v1", tags=["marketplace"])
webhook_router = APIRouter(prefix="/webhooks", tags=["payments"])
admin_router = APIRouter(
    prefix="/api/v1/admin/marketplace",
    tags=["marketplace-admin"],
    dependencies=[Depends(require_role(UserRole.SUPER_ADMIN))],
)


class OfferInput(BaseModel):
    description: str = Field(default="", max_length=4000)
    price_usd: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    platform_fee_usd: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    escrow_credit_usd: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    duration_days: int = Field(default=30, ge=1, le=366)
    minimum_wallet_usd: Decimal = Field(
        default=Decimal("10.00"), ge=0, max_digits=18, decimal_places=2
    )
    profit_share_rate: Decimal = Field(
        default=Decimal("0.10"), ge=0, le=1, max_digits=9, decimal_places=6
    )
    is_published: bool = False

    @field_validator("escrow_credit_usd")
    @classmethod
    def _split_is_valid(cls, value: Decimal, info: Any) -> Decimal:
        price = info.data.get("price_usd")
        fee = info.data.get("platform_fee_usd")
        if price is not None and fee is not None and fee + value != price:
            raise ValueError("platform fee plus escrow credit must equal the price")
        return value


class VerifyPaymentInput(BaseModel):
    razorpay_order_id: str = Field(min_length=4, max_length=80)
    razorpay_payment_id: str = Field(min_length=4, max_length=80)
    razorpay_signature: str = Field(min_length=32, max_length=160)


class TopUpInput(BaseModel):
    amount_usd: Decimal = Field(gt=0, max_digits=18, decimal_places=2)


class Mt5CredentialInput(BaseModel):
    login: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=512)
    server: str = Field(min_length=1, max_length=160)
    provider_name: str = Field(default="MetaTrader 5", min_length=1, max_length=120)
    category: AccountCategory = AccountCategory.DEMO
    transport: AccountTransport = AccountTransport.NATIVE_MT5
    external_account_ref: str | None = Field(default=None, max_length=160)

    @field_validator("transport")
    @classmethod
    def _supported_transport(cls, value: AccountTransport) -> AccountTransport:
        if value is AccountTransport.METAAPI:
            raise ValueError("MetaApi enrollment execution is not configured")
        return value


class ManualActivationInput(BaseModel):
    user_id: uuid.UUID
    strategy_id: uuid.UUID
    idempotency_key: str = Field(min_length=8, max_length=256)
    reason: str | None = Field(default=None, max_length=240)


class WalletAdjustmentInput(BaseModel):
    amount_usd: Decimal = Field(max_digits=18, decimal_places=2)
    idempotency_key: str = Field(min_length=8, max_length=256)
    reason: str = Field(min_length=1, max_length=240)

    @field_validator("amount_usd")
    @classmethod
    def _non_zero(cls, value: Decimal) -> Decimal:
        if value == 0:
            raise ValueError("amount must not be zero")
        return value


def _subject(claims: Claims) -> uuid.UUID:
    try:
        return uuid.UUID(claims.subject)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="invalid identity subject") from exc


def _user(db: Session, user_id: uuid.UUID) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    return user


def _idempotency(value: str | None) -> str:
    if not value or not 8 <= len(value) <= 256:
        raise HTTPException(status_code=422, detail="Idempotency-Key must be 8 to 256 characters")
    return value


def _wallet_balance(db: Session, enrollment_id: uuid.UUID) -> Decimal:
    result = db.scalar(
        select(func.coalesce(func.sum(EscrowLedgerEntry.amount), Decimal("0"))).where(
            EscrowLedgerEntry.enrollment_id == enrollment_id
        )
    )
    return Decimal(result if result is not None else Decimal("0"))


def _offer_view(strategy: Strategy, offer: StrategyOffer) -> dict[str, Any]:
    return {
        "strategy_id": str(strategy.id),
        "strategy_key": strategy.strategy_key,
        "strategy_version": strategy.strategy_version,
        "name": strategy.name,
        "description": offer.description,
        "price_usd": format(offer.price_usd, "f"),
        "platform_fee_usd": format(offer.platform_fee_usd, "f"),
        "escrow_credit_usd": format(offer.escrow_credit_usd, "f"),
        "duration_days": offer.duration_days,
        "minimum_wallet_usd": format(offer.minimum_wallet_usd, "f"),
        "profit_share_rate": format(offer.profit_share_rate, "f"),
        "is_published": offer.is_published,
    }


def _enrollment_view(
    db: Session, enrollment: StrategyEnrollment, strategy: Strategy
) -> dict[str, Any]:
    account = db.scalar(
        select(EnrollmentAccount).where(EnrollmentAccount.enrollment_id == enrollment.id)
    )
    latest_purchase = db.scalar(
        select(StrategyPurchase)
        .where(
            StrategyPurchase.enrollment_id == enrollment.id,
            StrategyPurchase.status == PaymentStatus.PAID.value,
        )
        .order_by(StrategyPurchase.ends_at.desc())
    )
    balance = _wallet_balance(db, enrollment.id)
    return {
        "id": str(enrollment.id),
        "strategy_id": str(strategy.id),
        "strategy_key": strategy.strategy_key,
        "strategy_version": strategy.strategy_version,
        "strategy_name": strategy.name,
        "status": enrollment.status,
        "wallet": {
            "currency": "USD",
            "balance": format(balance, "f"),
            "minimum": format(enrollment.minimum_wallet_usd, "f"),
            "entry_allowed": balance >= enrollment.minimum_wallet_usd,
        },
        "profit_share_rate": format(enrollment.profit_share_rate, "f"),
        "access_ends_at": latest_purchase.ends_at.isoformat() if latest_purchase else None,
        "account": None
        if account is None
        else {
            "provider_name": account.provider_name,
            "server_identifier": account.server_identifier,
            "category": account.category,
            "transport": account.transport,
            "status": account.status,
            "external_account_ref": account.external_account_ref,
            "credential_configured": bool(account.credential_key_ref),
            "worker_status": "HEALTHY"
            if account.worker_heartbeat_at
            and (datetime.now(UTC) - account.worker_heartbeat_at).total_seconds() <= 90
            else "NO_WORKER",
        },
    }


def _ensure_enrollment(
    db: Session, *, user_id: uuid.UUID, strategy: Strategy, offer: StrategyOffer
) -> StrategyEnrollment:
    enrollment = db.scalar(
        select(StrategyEnrollment).where(
            StrategyEnrollment.user_id == user_id,
            StrategyEnrollment.strategy_id == strategy.id,
        )
    )
    if enrollment is None:
        enrollment = StrategyEnrollment(
            user_id=user_id,
            strategy_id=strategy.id,
            status=EnrollmentStatus.CREDENTIALS_REQUIRED.value,
            minimum_wallet_usd=offer.minimum_wallet_usd,
            profit_share_rate=offer.profit_share_rate,
        )
        db.add(enrollment)
        db.flush()
    return enrollment


def _period_bounds(
    db: Session, enrollment_id: uuid.UUID, duration_days: int
) -> tuple[datetime, datetime]:
    now = datetime.now(UTC)
    latest_end = db.scalar(
        select(func.max(StrategyPurchase.ends_at)).where(
            StrategyPurchase.enrollment_id == enrollment_id,
            StrategyPurchase.status == PaymentStatus.PAID.value,
        )
    )
    start = max(now, latest_end) if latest_end else now
    return start, start + timedelta(days=duration_days)


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


def _credit_escrow(
    db: Session,
    *,
    enrollment_id: uuid.UUID,
    purchase_id: uuid.UUID | None,
    amount: Decimal,
    entry_type: str,
    idempotency_key: str,
    reason: str,
    actor: str,
) -> None:
    if db.scalar(
        select(EscrowLedgerEntry).where(EscrowLedgerEntry.idempotency_key == idempotency_key)
    ):
        return
    db.add(
        EscrowLedgerEntry(
            enrollment_id=enrollment_id,
            purchase_id=purchase_id,
            entry_type=entry_type,
            amount=amount,
            idempotency_key=idempotency_key,
            reason=reason,
            actor=actor,
        )
    )


def _assert_account_identity_available(
    db: Session,
    *,
    account: EnrollmentAccount,
    server: str,
    login: str,
    account_ref: str,
) -> None:
    same_broker = db.scalar(
        select(EnrollmentAccount.id).where(
            EnrollmentAccount.id != account.id,
            EnrollmentAccount.server_identifier == server,
            EnrollmentAccount.broker_login == login,
        )
    )
    if same_broker is not None:
        raise HTTPException(
            status_code=409, detail="this MT5 login is already assigned to another strategy account"
        )
    same_ref = db.scalar(
        select(EnrollmentAccount.id).where(
            EnrollmentAccount.id != account.id,
            EnrollmentAccount.external_account_ref == account_ref,
        )
    )
    if same_ref is not None:
        raise HTTPException(
            status_code=409, detail="this execution account reference is already assigned"
        )


def _ensure_assignment(db: Session, enrollment: StrategyEnrollment) -> None:
    """Create the conservative default fan-out assignment exactly once."""
    assignment = db.scalar(
        select(StrategyAssignment).where(
            StrategyAssignment.user_id == enrollment.user_id,
            StrategyAssignment.strategy_id == enrollment.strategy_id,
        )
    )
    if assignment is None:
        db.add(
            StrategyAssignment(
                user_id=enrollment.user_id,
                strategy_id=enrollment.strategy_id,
                master_lot=Decimal("0.01"),
                multiplier=Decimal("1.0000"),
                multiplier_min=Decimal("0.1000"),
                multiplier_max=Decimal("2.0000"),
                status="ACTIVE",
            )
        )


def _fulfill_payment_order(
    db: Session,
    *,
    order: PaymentOrder,
    payment_id: str,
    actor: str,
) -> None:
    if order.status == PaymentStatus.PAID.value:
        if order.razorpay_payment_id and order.razorpay_payment_id != payment_id:
            raise HTTPException(
                status_code=409, detail="payment order already fulfilled by another payment"
            )
        return
    order.status = PaymentStatus.PAID.value
    order.razorpay_payment_id = payment_id
    order.paid_at = datetime.now(UTC)
    if order.purpose == PaymentPurpose.STRATEGY_PURCHASE.value:
        if order.purchase_id is None:
            raise HTTPException(
                status_code=500, detail="purchase payment is missing purchase reference"
            )
        purchase = db.get(StrategyPurchase, order.purchase_id)
        if purchase is None:
            raise HTTPException(status_code=500, detail="purchase not found")
        purchase.status = PaymentStatus.PAID.value
        purchase.razorpay_payment_id = payment_id
        purchase.paid_at = order.paid_at
        _credit_escrow(
            db,
            enrollment_id=order.enrollment_id,
            purchase_id=purchase.id,
            amount=purchase.escrow_credit_usd,
            entry_type="PURCHASE_ESCROW_CREDIT",
            idempotency_key=f"purchase-credit:{purchase.id}",
            reason="Strategy purchase escrow credit",
            actor=actor,
        )
        enrollment = db.get(StrategyEnrollment, order.enrollment_id)
        if enrollment is not None:
            _ensure_assignment(db, enrollment)
        if enrollment is not None and enrollment.status == EnrollmentStatus.EXPIRED.value:
            enrollment.status = EnrollmentStatus.CREDENTIALS_REQUIRED.value
    elif order.purpose == PaymentPurpose.WALLET_TOP_UP.value:
        _credit_escrow(
            db,
            enrollment_id=order.enrollment_id,
            purchase_id=None,
            amount=order.amount_usd,
            entry_type="TOP_UP",
            idempotency_key=f"topup-credit:{order.id}",
            reason="Escrow top-up",
            actor=actor,
        )
    _audit(
        db,
        event_type="payment.fulfilled",
        entity_type="payment_order",
        entity_id=str(order.id),
        actor=actor,
        data={
            "purpose": order.purpose,
            "amount_usd": format(order.amount_usd, "f"),
            "enrollment_id": str(order.enrollment_id),
        },
    )


@lru_cache
def _local_vault() -> MockCredentialVault:
    return MockCredentialVault()


def _gateway(settings: Settings) -> RazorpayGateway:
    return RazorpayGateway(settings)


@router.get("/marketplace/strategies")
def list_marketplace(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    rows = db.execute(
        select(Strategy, StrategyOffer)
        .join(StrategyOffer, StrategyOffer.strategy_id == Strategy.id)
        .where(Strategy.is_active.is_(True), StrategyOffer.is_published.is_(True))
        .order_by(Strategy.name)
    ).all()
    return [_offer_view(strategy, offer) for strategy, offer in rows]


@router.get("/marketplace/enrollments")
def list_enrollments(
    db: Session = Depends(get_db), claims: Claims = Depends(current_claims)
) -> list[dict[str, Any]]:
    user_id = _subject(claims)
    rows = db.execute(
        select(StrategyEnrollment, Strategy)
        .join(Strategy, StrategyEnrollment.strategy_id == Strategy.id)
        .where(StrategyEnrollment.user_id == user_id)
        .order_by(StrategyEnrollment.created_at.desc())
    ).all()
    return [_enrollment_view(db, enrollment, strategy) for enrollment, strategy in rows]


@router.post("/marketplace/strategies/{strategy_id}/checkout", status_code=status.HTTP_201_CREATED)
def create_purchase_checkout(
    strategy_id: uuid.UUID,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    claims: Claims = Depends(current_claims),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    key = _idempotency(idempotency_key)
    user_id = _subject(claims)
    _user(db, user_id)
    strategy = db.get(Strategy, strategy_id)
    offer = db.scalar(select(StrategyOffer).where(StrategyOffer.strategy_id == strategy_id))
    if strategy is None or offer is None or not strategy.is_active or not offer.is_published:
        raise HTTPException(status_code=404, detail="strategy is not available")
    order_key = f"purchase:{user_id}:{strategy_id}:{key}"
    existing = db.scalar(select(PaymentOrder).where(PaymentOrder.idempotency_key == order_key))
    if existing is not None:
        if existing.razorpay_order_id is None:
            raise HTTPException(
                status_code=409, detail="checkout is pending provider order creation"
            )
        return {
            "payment_order_id": str(existing.id),
            "razorpay_order_id": existing.razorpay_order_id,
            "key_id": _gateway(settings).public_key_id,
            "amount_usd": format(existing.amount_usd, "f"),
            "currency": "USD",
            "replayed": True,
        }
    gateway = _gateway(settings)
    if not gateway.configured:
        raise HTTPException(status_code=503, detail="Razorpay test credentials are not configured")
    enrollment = _ensure_enrollment(db, user_id=user_id, strategy=strategy, offer=offer)
    starts_at, ends_at = _period_bounds(db, enrollment.id, offer.duration_days)
    purchase = StrategyPurchase(
        enrollment_id=enrollment.id,
        source=PurchaseSource.RAZORPAY.value,
        status=PaymentStatus.PENDING.value,
        price_usd=offer.price_usd,
        platform_fee_usd=offer.platform_fee_usd,
        escrow_credit_usd=offer.escrow_credit_usd,
        starts_at=starts_at,
        ends_at=ends_at,
        idempotency_key=f"purchase:{user_id}:{strategy_id}:{key}",
    )
    db.add(purchase)
    db.flush()
    try:
        provider_order = gateway.create_order(
            amount_usd=offer.price_usd,
            receipt=f"ptx-{str(purchase.id)[:24]}",
            notes={
                "purchase_id": str(purchase.id),
                "enrollment_id": str(enrollment.id),
                "purpose": "strategy_purchase",
            },
        )
    except RazorpayError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if provider_order.currency != "USD" or provider_order.amount_subunits != usd_to_subunits(
        offer.price_usd
    ):
        raise HTTPException(status_code=502, detail="Razorpay returned an unexpected order amount")
    purchase.razorpay_order_id = provider_order.order_id
    payment_order = PaymentOrder(
        enrollment_id=enrollment.id,
        purchase_id=purchase.id,
        purpose=PaymentPurpose.STRATEGY_PURCHASE.value,
        status=PaymentStatus.PENDING.value,
        amount_usd=offer.price_usd,
        razorpay_order_id=provider_order.order_id,
        idempotency_key=order_key,
    )
    db.add(payment_order)
    _audit(
        db,
        event_type="payment.order_created",
        entity_type="payment_order",
        entity_id=str(payment_order.id),
        actor=claims.subject,
        data={"purpose": payment_order.purpose, "amount_usd": format(offer.price_usd, "f")},
    )
    return {
        "payment_order_id": str(payment_order.id),
        "razorpay_order_id": provider_order.order_id,
        "key_id": gateway.public_key_id,
        "amount_usd": format(offer.price_usd, "f"),
        "currency": "USD",
        "replayed": False,
    }


@router.post(
    "/marketplace/enrollments/{enrollment_id}/top-ups", status_code=status.HTTP_201_CREATED
)
def create_top_up_checkout(
    enrollment_id: uuid.UUID,
    body: TopUpInput,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    claims: Claims = Depends(current_claims),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    key = _idempotency(idempotency_key)
    user_id = _subject(claims)
    enrollment = db.get(StrategyEnrollment, enrollment_id)
    if enrollment is None or enrollment.user_id != user_id:
        raise HTTPException(status_code=404, detail="strategy enrollment not found")
    gateway = _gateway(settings)
    if not gateway.configured:
        raise HTTPException(status_code=503, detail="Razorpay test credentials are not configured")
    order_key = f"topup:{enrollment_id}:{key}"
    existing = db.scalar(select(PaymentOrder).where(PaymentOrder.idempotency_key == order_key))
    if existing is not None and existing.razorpay_order_id:
        return {
            "payment_order_id": str(existing.id),
            "razorpay_order_id": existing.razorpay_order_id,
            "key_id": gateway.public_key_id,
            "amount_usd": format(existing.amount_usd, "f"),
            "currency": "USD",
            "replayed": True,
        }
    try:
        provider_order = gateway.create_order(
            amount_usd=body.amount_usd,
            receipt=f"ptx-topup-{str(enrollment.id)[:16]}",
            notes={"enrollment_id": str(enrollment.id), "purpose": "wallet_top_up"},
        )
    except RazorpayError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if provider_order.currency != "USD" or provider_order.amount_subunits != usd_to_subunits(
        body.amount_usd
    ):
        raise HTTPException(status_code=502, detail="Razorpay returned an unexpected order amount")
    order = PaymentOrder(
        enrollment_id=enrollment.id,
        purpose=PaymentPurpose.WALLET_TOP_UP.value,
        status=PaymentStatus.PENDING.value,
        amount_usd=body.amount_usd,
        razorpay_order_id=provider_order.order_id,
        idempotency_key=order_key,
    )
    db.add(order)
    _audit(
        db,
        event_type="payment.order_created",
        entity_type="payment_order",
        entity_id=str(order.id),
        actor=claims.subject,
        data={"purpose": order.purpose, "amount_usd": format(body.amount_usd, "f")},
    )
    return {
        "payment_order_id": str(order.id),
        "razorpay_order_id": provider_order.order_id,
        "key_id": gateway.public_key_id,
        "amount_usd": format(body.amount_usd, "f"),
        "currency": "USD",
        "replayed": False,
    }


@router.post("/payments/razorpay/verify")
def verify_payment(
    body: VerifyPaymentInput,
    db: Session = Depends(get_db),
    claims: Claims = Depends(current_claims),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    gateway = _gateway(settings)
    order = db.scalar(
        select(PaymentOrder).where(PaymentOrder.razorpay_order_id == body.razorpay_order_id)
    )
    if order is None:
        raise HTTPException(status_code=404, detail="payment order not found")
    enrollment = db.get(StrategyEnrollment, order.enrollment_id)
    if enrollment is None or enrollment.user_id != _subject(claims):
        raise HTTPException(status_code=404, detail="payment order not found")
    if not gateway.verify_checkout_signature(
        order_id=body.razorpay_order_id,
        payment_id=body.razorpay_payment_id,
        signature=body.razorpay_signature,
    ):
        raise HTTPException(status_code=400, detail="invalid Razorpay payment signature")
    try:
        payment = gateway.fetch_payment(body.razorpay_payment_id)
    except RazorpayError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if (
        payment.get("order_id") != body.razorpay_order_id
        or payment.get("status") != "captured"
        or payment.get("currency") != "USD"
        or payment.get("amount") != usd_to_subunits(order.amount_usd)
    ):
        raise HTTPException(status_code=409, detail="payment is not captured for this order amount")
    _fulfill_payment_order(
        db, order=order, payment_id=body.razorpay_payment_id, actor=claims.subject
    )
    return {
        "payment_order_id": str(order.id),
        "status": order.status,
        "enrollment_id": str(order.enrollment_id),
    }


@router.post("/marketplace/enrollments/{enrollment_id}/mt5-credentials")
def save_mt5_credentials(
    enrollment_id: uuid.UUID,
    body: Mt5CredentialInput,
    db: Session = Depends(get_db),
    claims: Claims = Depends(current_claims),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    if settings.is_production:
        raise HTTPException(
            status_code=503,
            detail=(
                "a production credential vault must be configured before MT5 "
                "credentials can be saved"
            ),
        )
    enrollment = db.get(StrategyEnrollment, enrollment_id)
    if enrollment is None or enrollment.user_id != _subject(claims):
        raise HTTPException(status_code=404, detail="strategy enrollment not found")
    account = db.scalar(
        select(EnrollmentAccount).where(EnrollmentAccount.enrollment_id == enrollment.id)
    )
    if account is None:
        account = EnrollmentAccount(
            enrollment_id=enrollment.id,
            provider_name=body.provider_name,
            server_identifier=body.server,
            category=body.category.value,
            transport=body.transport.value,
            status=TradingAccountStatus.DISABLED.value,
            external_account_ref=body.external_account_ref,
        )
        db.add(account)
        db.flush()
    account_ref = body.external_account_ref or f"enrollment-{enrollment.id}"
    _assert_account_identity_available(
        db, account=account, server=body.server, login=body.login, account_ref=account_ref
    )
    try:
        account.credential_key_ref = _local_vault().store_mt5_credentials(
            account_ref=str(account.id),
            login=body.login,
            password=body.password,
            server=body.server,
        )
    except VaultError as exc:
        raise HTTPException(status_code=422, detail="invalid MT5 credential input") from exc
    account.provider_name = body.provider_name
    account.server_identifier = body.server
    account.broker_login = body.login
    account.category = body.category.value
    account.transport = body.transport.value
    account.external_account_ref = account_ref
    account.status = TradingAccountStatus.ACTIVE.value
    enrollment.status = EnrollmentStatus.ACTIVE.value
    _audit(
        db,
        event_type="enrollment_account.credentials_updated",
        entity_type="enrollment_account",
        entity_id=str(account.id),
        actor=claims.subject,
        data={
            "enrollment_id": str(enrollment.id),
            "transport": account.transport,
            "category": account.category,
        },
    )
    return {
        "enrollment_id": str(enrollment.id),
        "credential_configured": True,
        "account_status": account.status,
    }


@router.get("/marketplace/enrollments/{enrollment_id}/settlements")
def list_settlements(
    enrollment_id: uuid.UUID,
    db: Session = Depends(get_db),
    claims: Claims = Depends(current_claims),
) -> list[dict[str, Any]]:
    enrollment = db.get(StrategyEnrollment, enrollment_id)
    if enrollment is None or enrollment.user_id != _subject(claims):
        raise HTTPException(status_code=404, detail="strategy enrollment not found")
    rows = db.scalars(
        select(StrategySettlement)
        .where(StrategySettlement.enrollment_id == enrollment.id)
        .order_by(StrategySettlement.period_start.desc())
    ).all()
    return [
        {
            "id": str(row.id),
            "period_start": row.period_start.isoformat(),
            "period_end": row.period_end.isoformat(),
            "net_closed_realized_pnl": format(row.net_closed_realized_pnl, "f"),
            "profit_share_rate": format(row.profit_share_rate, "f"),
            "profit_share_due": format(row.profit_share_due, "f"),
        }
        for row in rows
    ]


@webhook_router.post("/razorpay")
async def razorpay_webhook(
    request: Request,
    x_razorpay_signature: str | None = Header(default=None),
    x_razorpay_event_id: str | None = Header(default=None),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, bool]:
    raw_body = await request.body()
    gateway = _gateway(settings)
    if not gateway.verify_webhook_signature(raw_body=raw_body, signature=x_razorpay_signature):
        raise HTTPException(status_code=401, detail="invalid Razorpay webhook signature")
    if not x_razorpay_event_id:
        raise HTTPException(status_code=400, detail="missing Razorpay event id")
    if db.scalar(select(PaymentEvent).where(PaymentEvent.provider_event_id == x_razorpay_event_id)):
        return {"ok": True, "replayed": True}
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="invalid JSON webhook body") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="invalid webhook payload")
    event_type = str(payload.get("event", ""))
    db.add(
        PaymentEvent(provider_event_id=x_razorpay_event_id, event_type=event_type, payload=payload)
    )
    payment = payload.get("payload", {}).get("payment", {}).get("entity", {})
    if event_type == "payment.captured" and isinstance(payment, dict):
        order_id = payment.get("order_id")
        payment_id = payment.get("id")
        order = (
            db.scalar(select(PaymentOrder).where(PaymentOrder.razorpay_order_id == order_id))
            if isinstance(order_id, str)
            else None
        )
        if (
            order is not None
            and isinstance(payment_id, str)
            and payment.get("currency") == "USD"
            and payment.get("amount") == usd_to_subunits(order.amount_usd)
        ):
            _fulfill_payment_order(db, order=order, payment_id=payment_id, actor="razorpay-webhook")
    return {"ok": True, "replayed": False}


@admin_router.put("/strategies/{strategy_id}/offer")
def upsert_offer(
    strategy_id: uuid.UUID,
    body: OfferInput,
    db: Session = Depends(get_db),
    claims: Claims = Depends(current_claims),
) -> dict[str, Any]:
    strategy = db.get(Strategy, strategy_id)
    if strategy is None:
        raise HTTPException(status_code=404, detail="strategy not found")
    offer = db.scalar(select(StrategyOffer).where(StrategyOffer.strategy_id == strategy.id))
    if offer is None:
        offer = StrategyOffer(strategy_id=strategy.id, **body.model_dump())
        db.add(offer)
    else:
        for field, value in body.model_dump().items():
            setattr(offer, field, value)
    db.flush()
    _audit(
        db,
        event_type="marketplace.offer_updated",
        entity_type="strategy_offer",
        entity_id=str(offer.id),
        actor=claims.subject,
        data={
            "strategy_id": str(strategy.id),
            "price_usd": format(offer.price_usd, "f"),
            "published": offer.is_published,
        },
    )
    return _offer_view(strategy, offer)


@admin_router.get("/offers")
def list_offers_for_admin(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    rows = db.execute(
        select(Strategy, StrategyOffer)
        .join(StrategyOffer, StrategyOffer.strategy_id == Strategy.id)
        .order_by(Strategy.name)
    ).all()
    return [_offer_view(strategy, offer) for strategy, offer in rows]


@admin_router.get("/enrollments")
def list_enrollments_for_admin(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    rows = db.execute(
        select(StrategyEnrollment, Strategy, User)
        .join(Strategy, StrategyEnrollment.strategy_id == Strategy.id)
        .join(User, StrategyEnrollment.user_id == User.id)
        .order_by(StrategyEnrollment.created_at.desc())
    ).all()
    return [
        {
            **_enrollment_view(db, enrollment, strategy),
            "user_id": str(user.id),
            "user_email": user.email,
            "user_display_name": user.display_name,
        }
        for enrollment, strategy, user in rows
    ]


@admin_router.post("/manual-activations", status_code=status.HTTP_201_CREATED)
def manual_activate(
    body: ManualActivationInput,
    db: Session = Depends(get_db),
    claims: Claims = Depends(current_claims),
) -> dict[str, Any]:
    _user(db, body.user_id)
    strategy = db.get(Strategy, body.strategy_id)
    offer = db.scalar(select(StrategyOffer).where(StrategyOffer.strategy_id == body.strategy_id))
    if strategy is None or offer is None:
        raise HTTPException(status_code=404, detail="strategy offer not found")
    purchase_key = f"admin-activation:{body.user_id}:{body.strategy_id}:{body.idempotency_key}"
    existing = db.scalar(
        select(StrategyPurchase).where(StrategyPurchase.idempotency_key == purchase_key)
    )
    if existing is not None:
        return {
            "purchase_id": str(existing.id),
            "enrollment_id": str(existing.enrollment_id),
            "replayed": True,
        }
    enrollment = _ensure_enrollment(db, user_id=body.user_id, strategy=strategy, offer=offer)
    _ensure_assignment(db, enrollment)
    starts_at, ends_at = _period_bounds(db, enrollment.id, offer.duration_days)
    purchase = StrategyPurchase(
        enrollment_id=enrollment.id,
        source=PurchaseSource.ADMIN.value,
        status=PaymentStatus.PAID.value,
        price_usd=offer.price_usd,
        platform_fee_usd=offer.platform_fee_usd,
        escrow_credit_usd=offer.escrow_credit_usd,
        starts_at=starts_at,
        ends_at=ends_at,
        idempotency_key=purchase_key,
        paid_at=datetime.now(UTC),
    )
    db.add(purchase)
    db.flush()
    _credit_escrow(
        db,
        enrollment_id=enrollment.id,
        purchase_id=purchase.id,
        amount=purchase.escrow_credit_usd,
        entry_type="PURCHASE_ESCROW_CREDIT",
        idempotency_key=f"purchase-credit:{purchase.id}",
        reason=body.reason or "Manual strategy activation escrow credit",
        actor=claims.subject,
    )
    _audit(
        db,
        event_type="marketplace.manual_activation",
        entity_type="strategy_purchase",
        entity_id=str(purchase.id),
        actor=claims.subject,
        data={
            "user_id": str(body.user_id),
            "strategy_id": str(body.strategy_id),
            "escrow_credit_usd": format(purchase.escrow_credit_usd, "f"),
        },
    )
    return {"purchase_id": str(purchase.id), "enrollment_id": str(enrollment.id), "replayed": False}


@admin_router.post("/enrollments/{enrollment_id}/wallet-adjustments")
def adjust_wallet(
    enrollment_id: uuid.UUID,
    body: WalletAdjustmentInput,
    db: Session = Depends(get_db),
    claims: Claims = Depends(current_claims),
) -> dict[str, Any]:
    enrollment = db.get(StrategyEnrollment, enrollment_id)
    if enrollment is None:
        raise HTTPException(status_code=404, detail="strategy enrollment not found")
    key = f"admin-adjustment:{enrollment.id}:{body.idempotency_key}"
    _credit_escrow(
        db,
        enrollment_id=enrollment.id,
        purchase_id=None,
        amount=body.amount_usd,
        entry_type="ADMIN_ADJUSTMENT",
        idempotency_key=key,
        reason=body.reason,
        actor=claims.subject,
    )
    _audit(
        db,
        event_type="marketplace.wallet_adjusted",
        entity_type="strategy_enrollment",
        entity_id=str(enrollment.id),
        actor=claims.subject,
        data={"amount_usd": format(body.amount_usd, "f"), "reason": body.reason},
    )
    return {
        "enrollment_id": str(enrollment.id),
        "balance": format(_wallet_balance(db, enrollment.id), "f"),
    }


@admin_router.put("/enrollments/{enrollment_id}/mt5-credentials")
def update_enrollment_credentials_as_admin(
    enrollment_id: uuid.UUID,
    body: Mt5CredentialInput,
    db: Session = Depends(get_db),
    claims: Claims = Depends(current_claims),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    if settings.is_production:
        raise HTTPException(
            status_code=503,
            detail=(
                "a production credential vault must be configured before MT5 "
                "credentials can be saved"
            ),
        )
    enrollment = db.get(StrategyEnrollment, enrollment_id)
    if enrollment is None:
        raise HTTPException(status_code=404, detail="strategy enrollment not found")
    account = db.scalar(
        select(EnrollmentAccount).where(EnrollmentAccount.enrollment_id == enrollment.id)
    )
    if account is None:
        account = EnrollmentAccount(
            enrollment_id=enrollment.id,
            provider_name=body.provider_name,
            server_identifier=body.server,
            category=body.category.value,
            transport=body.transport.value,
            status=TradingAccountStatus.DISABLED.value,
            external_account_ref=body.external_account_ref,
        )
        db.add(account)
        db.flush()
    account_ref = body.external_account_ref or f"enrollment-{enrollment.id}"
    _assert_account_identity_available(
        db, account=account, server=body.server, login=body.login, account_ref=account_ref
    )
    try:
        account.credential_key_ref = _local_vault().store_mt5_credentials(
            account_ref=str(account.id),
            login=body.login,
            password=body.password,
            server=body.server,
        )
    except VaultError as exc:
        raise HTTPException(status_code=422, detail="invalid MT5 credential input") from exc
    account.provider_name, account.server_identifier = body.provider_name, body.server
    account.broker_login = body.login
    account.category, account.transport, account.status = (
        body.category.value,
        body.transport.value,
        TradingAccountStatus.ACTIVE.value,
    )
    account.external_account_ref = account_ref
    enrollment.status = EnrollmentStatus.ACTIVE.value
    _audit(
        db,
        event_type="enrollment_account.credentials_admin_updated",
        entity_type="enrollment_account",
        entity_id=str(account.id),
        actor=claims.subject,
        data={
            "enrollment_id": str(enrollment.id),
            "category": account.category,
            "transport": account.transport,
        },
    )
    return {
        "enrollment_id": str(enrollment.id),
        "credential_configured": True,
        "account_status": account.status,
    }
