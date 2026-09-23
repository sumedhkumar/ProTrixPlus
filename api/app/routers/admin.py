"""Super-admin-only read APIs.

The whole router is gated: ``dependencies=[Depends(require_role(SUPER_ADMIN))]``.
A USER token gets 403 on every path here.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from protrix_contracts.db.models import UserRole
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.email import EmailSender, get_email_sender
from app.identity import Claims
from app.security import current_claims, require_role
from app.services import alerts, marketplace, mt5_connection, notifications, payments, read_models

router = APIRouter(
    prefix="/api/v1/admin",
    tags=["admin"],
    dependencies=[Depends(require_role(UserRole.SUPER_ADMIN))],
)


@router.get("/users")
def users(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return read_models.list_users(db)


@router.get("/assignments")
def assignments(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return read_models.list_assignments(db)


@router.get("/ops-summary")
def ops_summary(db: Session = Depends(get_db)) -> dict[str, Any]:
    return read_models.ops_summary(db)


@router.get("/mt5-connections")
def admin_mt5_connections(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return mt5_connection.admin_list_connections(db)


class SetMetaApiAccountRequest(BaseModel):
    metaapi_account_id: str = Field(min_length=1, max_length=64)
    metaapi_region: str = Field(min_length=1, max_length=32)


@router.patch("/mt5-connections/{connection_id}/metaapi")
def admin_set_metaapi_account(
    connection_id: str, body: SetMetaApiAccountRequest, db: Session = Depends(get_db)
) -> dict[str, Any]:
    try:
        return mt5_connection.admin_set_metaapi_account(
            db,
            connection_id,
            metaapi_account_id=body.metaapi_account_id,
            metaapi_region=body.metaapi_region,
        )
    except mt5_connection.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


# --------------------------------------------------------------------------
# Strategy catalog (PRD 4.3, 5.3, 6)
# --------------------------------------------------------------------------


class StrategyCreateRequest(BaseModel):
    strategy_key: str = Field(min_length=1, max_length=64)
    strategy_version: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    symbol: str | None = Field(default=None, max_length=32)
    timeframe: str | None = Field(default=None, max_length=8)
    price: Decimal | None = Field(default=None, ge=0)
    profit_share_percent: Decimal | None = Field(default=None, ge=0, le=100)
    base_lot: Decimal | None = Field(default=None, gt=0)
    win_rate: Decimal | None = Field(default=None, ge=0, le=100)
    max_drawdown: Decimal | None = Field(default=None, ge=0, le=100)
    description_short: str | None = Field(default=None, max_length=240)


class StrategyUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    symbol: str | None = Field(default=None, max_length=32)
    timeframe: str | None = Field(default=None, max_length=8)
    price: Decimal | None = Field(default=None, ge=0)
    profit_share_percent: Decimal | None = Field(default=None, ge=0, le=100)
    base_lot: Decimal | None = Field(default=None, gt=0)
    win_rate: Decimal | None = Field(default=None, ge=0, le=100)
    max_drawdown: Decimal | None = Field(default=None, ge=0, le=100)
    description_short: str | None = Field(default=None, max_length=240)
    is_active: bool | None = None


@router.get("/strategies")
def admin_list_strategies(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return marketplace.list_catalog(db)


@router.post("/strategies", status_code=status.HTTP_201_CREATED)
def admin_create_strategy(
    body: StrategyCreateRequest, db: Session = Depends(get_db)
) -> dict[str, Any]:
    return marketplace.admin_create_strategy(
        db,
        marketplace.StrategyCatalogInput(
            strategy_key=body.strategy_key,
            strategy_version=body.strategy_version,
            name=body.name,
            description=body.description,
            symbol=body.symbol,
            timeframe=body.timeframe,
            price=body.price,
            profit_share_percent=body.profit_share_percent,
            base_lot=body.base_lot,
            win_rate=body.win_rate,
            max_drawdown=body.max_drawdown,
            description_short=body.description_short,
        ),
    )


@router.patch("/strategies/{strategy_id}")
def admin_update_strategy(
    strategy_id: str, body: StrategyUpdateRequest, db: Session = Depends(get_db)
) -> dict[str, Any]:
    try:
        return marketplace.admin_update_strategy(
            db, strategy_id, **body.model_dump(exclude_unset=True)
        )
    except marketplace.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except marketplace.ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.get("/strategies/{strategy_id}/alert-config")
def admin_alert_config(strategy_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return marketplace.alert_config_for_strategy(db, strategy_id)
    except marketplace.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


# --------------------------------------------------------------------------
# Alert catalog (Feature 1: capture + changelog) + bundling into a strategy
# (Feature 2). Alerts are admin-authored here, then pasted into TradingView -
# see app/services/alerts.py's module docstring for why.
# --------------------------------------------------------------------------


class AlertCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    symbol: str = Field(min_length=1, max_length=32)
    lot_size: Decimal = Field(gt=0)
    timeframe: str = Field(min_length=1, max_length=8)


class AlertUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    symbol: str | None = Field(default=None, min_length=1, max_length=32)
    lot_size: Decimal | None = Field(default=None, gt=0)
    timeframe: str | None = Field(default=None, min_length=1, max_length=8)


class BundleAlertsRequest(BaseModel):
    alert_ids: list[str]


@router.get("/alerts")
def admin_list_alerts(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return alerts.admin_list_alerts(db)


@router.post("/alerts", status_code=status.HTTP_201_CREATED)
def admin_create_alert(
    body: AlertCreateRequest,
    db: Session = Depends(get_db),
    claims: Claims = Depends(current_claims),
) -> dict[str, Any]:
    return alerts.admin_create_alert(
        db,
        alerts.AlertInput(
            name=body.name, symbol=body.symbol, lot_size=body.lot_size, timeframe=body.timeframe
        ),
        actor=claims.subject,
    )


@router.patch("/alerts/{alert_id}")
def admin_update_alert(
    alert_id: str,
    body: AlertUpdateRequest,
    db: Session = Depends(get_db),
    claims: Claims = Depends(current_claims),
) -> dict[str, Any]:
    try:
        return alerts.admin_update_alert(
            db, alert_id, actor=claims.subject, **body.model_dump(exclude_unset=True)
        )
    except alerts.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/alerts/{alert_id}/changelog")
def admin_alert_changelog(alert_id: str, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return alerts.admin_get_alert_changelog(db, alert_id)


@router.patch("/strategies/{strategy_id}/alerts")
def admin_bundle_alerts(
    strategy_id: str,
    body: BundleAlertsRequest,
    db: Session = Depends(get_db),
    claims: Claims = Depends(current_claims),
) -> list[dict[str, Any]]:
    try:
        return alerts.admin_bundle_alerts_into_strategy(
            db, strategy_id, body.alert_ids, actor=claims.subject
        )
    except alerts.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


# --------------------------------------------------------------------------
# Entitlement grant / override / revoke (PRD 4.1 step 5, 4.3 step 6, 5.8)
# --------------------------------------------------------------------------


class GrantEntitlementRequest(BaseModel):
    user_id: str
    strategy_id: str
    master_lot: Decimal = Field(gt=0)
    multiplier: Decimal = Field(default=Decimal("1"))
    multiplier_min: Decimal = Field(default=marketplace.DEFAULT_MULTIPLIER_MIN)
    multiplier_max: Decimal = Field(default=marketplace.DEFAULT_MULTIPLIER_MAX)
    expires_at: datetime | None = None


class UpdateAssignmentRequest(BaseModel):
    master_lot: Decimal | None = Field(default=None, gt=0)
    multiplier_min: Decimal | None = None
    multiplier_max: Decimal | None = None
    status: str | None = None
    payment_status: str | None = None
    expires_at: datetime | None = None
    revoke: bool = False  # convenience: sets payment_status=REVOKED in one call


@router.post("/assignments", status_code=status.HTTP_201_CREATED)
def admin_grant_entitlement(
    body: GrantEntitlementRequest, db: Session = Depends(get_db)
) -> dict[str, Any]:
    try:
        return marketplace.admin_grant_entitlement(
            db,
            user_id=body.user_id,
            strategy_id=body.strategy_id,
            master_lot=body.master_lot,
            multiplier=body.multiplier,
            multiplier_min=body.multiplier_min,
            multiplier_max=body.multiplier_max,
            expires_at=body.expires_at,
        )
    except marketplace.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.patch("/assignments/{assignment_id}")
def admin_update_assignment(
    assignment_id: str, body: UpdateAssignmentRequest, db: Session = Depends(get_db)
) -> dict[str, Any]:
    # exclude_unset, not just filtering None: `expires_at: null` (clear it) and
    # `expires_at` omitted (leave it alone) must be distinguishable, and only
    # exclude_unset preserves that distinction.
    fields = body.model_dump(exclude_unset=True, exclude={"revoke"})
    if body.revoke:
        fields["payment_status"] = "REVOKED"
    if "expires_at" not in fields:
        fields["expires_at"] = ...  # service-layer sentinel: don't touch

    try:
        return marketplace.admin_update_assignment(db, assignment_id, **fields)
    except marketplace.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/assignments/{assignment_id}/approve")
def admin_approve_subscription(
    assignment_id: str,
    db: Session = Depends(get_db),
    claims: Claims = Depends(current_claims),
) -> dict[str, Any]:
    """Confirms the client's self-subscribed strategy request was paid for
    (out-of-band for MVP) and unlocks the Setup Wizard for them:
    PENDING_APPROVAL -> SETUP_INCOMPLETE."""
    try:
        return marketplace.admin_approve_subscription(db, assignment_id, actor=claims.subject)
    except marketplace.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except marketplace.ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


# --------------------------------------------------------------------------
# Payment-proof (UTR) review for paid subscription packages
# --------------------------------------------------------------------------


class RejectPaymentSubmissionRequest(BaseModel):
    reason: str | None = None


@router.get("/payment-submissions")
def admin_payment_submissions(
    status: str | None = None, db: Session = Depends(get_db)
) -> list[dict[str, Any]]:
    return payments.admin_list_payment_submissions(db, status=status)


@router.post("/payment-submissions/{submission_id}/approve")
def admin_approve_payment_submission(
    submission_id: str,
    db: Session = Depends(get_db),
    claims: Claims = Depends(current_claims),
    sender: EmailSender = Depends(get_email_sender),
) -> dict[str, Any]:
    try:
        result = payments.admin_approve_payment_submission(
            db, submission_id=submission_id, reviewer_subject=claims.subject
        )
    except payments.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except payments.ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    user = result["user"]
    if result["created_new_account"]:
        notifications.send_payment_approved_new_account_email(
            sender,
            to=user.email,
            display_name=user.display_name,
            temp_password=result["temp_password"],
            package=user.subscription_package,
        )
    else:
        notifications.send_subscription_renewed_email(
            sender,
            to=user.email,
            display_name=user.display_name,
            package=user.subscription_package,
            new_end=user.subscription_end,
        )
    submission_dict: dict[str, Any] = result["submission"]
    return submission_dict


@router.post("/payment-submissions/{submission_id}/reject")
def admin_reject_payment_submission(
    submission_id: str,
    body: RejectPaymentSubmissionRequest,
    db: Session = Depends(get_db),
    claims: Claims = Depends(current_claims),
    sender: EmailSender = Depends(get_email_sender),
) -> dict[str, Any]:
    try:
        submission = payments.admin_reject_payment_submission(
            db, submission_id=submission_id, reviewer_subject=claims.subject, reason=body.reason
        )
    except payments.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except payments.ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    notifications.send_payment_rejected_email(
        sender, to=submission["email"], display_name=submission["name"], reason=body.reason
    )
    return submission
