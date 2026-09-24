"""Admin APIs, gated per functional role tier.

SUPER_ADMIN can reach every route here. Below it: OPERATIONS_ADMIN (users,
MT5 connections), STRATEGY_ADMIN (strategy/alert catalog), FINANCE_ADMIN
(payments, entitlements), and AUDITOR (read-only on every GET). A USER token
gets 403 on every path here.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from protrix_contracts.db.models import UserRole
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.email import EmailSender, get_email_sender
from app.identity import Claims
from app.security import current_claims, require_role
from app.services import (
    admin_accounts,
    alerts,
    marketplace,
    mt5_connection,
    notifications,
    payments,
    read_models,
)

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

# Per-route-group role gates. SUPER_ADMIN is included in every group so it can
# still reach everything; AUDITOR is added only to the read-only variants.
_SUPER = Depends(require_role(UserRole.SUPER_ADMIN))
_OPS = Depends(require_role(UserRole.SUPER_ADMIN, UserRole.OPERATIONS_ADMIN))
_OPS_READ = Depends(
    require_role(UserRole.SUPER_ADMIN, UserRole.OPERATIONS_ADMIN, UserRole.AUDITOR)
)
_STRATEGY = Depends(require_role(UserRole.SUPER_ADMIN, UserRole.STRATEGY_ADMIN))
_STRATEGY_READ = Depends(
    require_role(UserRole.SUPER_ADMIN, UserRole.STRATEGY_ADMIN, UserRole.AUDITOR)
)
_FINANCE = Depends(require_role(UserRole.SUPER_ADMIN, UserRole.FINANCE_ADMIN))
_FINANCE_READ = Depends(
    require_role(UserRole.SUPER_ADMIN, UserRole.FINANCE_ADMIN, UserRole.AUDITOR)
)
# users/assignments/mt5-connections are read together on the web app's Clients
# tab, which both ops (support context) and finance (who to grant entitlements
# to) need - so all three share this wider read group, plus the auditor.
_CLIENTS_READ = Depends(
    require_role(
        UserRole.SUPER_ADMIN, UserRole.OPERATIONS_ADMIN, UserRole.FINANCE_ADMIN, UserRole.AUDITOR
    )
)
# The Clients tab's entitlement-grant picker also needs the strategy list (not
# to edit strategies, just to name them), so /strategies GET is readable by
# everyone who can reach either the Clients tab or the Strategy tab.
_CLIENTS_READ_OR_STRATEGY_READ = Depends(
    require_role(
        UserRole.SUPER_ADMIN,
        UserRole.OPERATIONS_ADMIN,
        UserRole.FINANCE_ADMIN,
        UserRole.STRATEGY_ADMIN,
        UserRole.AUDITOR,
    )
)


@router.get("/users", dependencies=[_CLIENTS_READ])
def users(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return read_models.list_users(db)


@router.get("/assignments", dependencies=[_CLIENTS_READ])
def assignments(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return read_models.list_assignments(db)


@router.get("/ops-summary", dependencies=[_OPS_READ])
def ops_summary(db: Session = Depends(get_db)) -> dict[str, Any]:
    return read_models.ops_summary(db)


@router.get("/mt5-connections", dependencies=[_CLIENTS_READ])
def admin_mt5_connections(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return mt5_connection.admin_list_connections(db)


class SetMetaApiAccountRequest(BaseModel):
    metaapi_account_id: str = Field(min_length=1, max_length=64)
    metaapi_region: str = Field(min_length=1, max_length=32)


@router.patch("/mt5-connections/{connection_id}/metaapi", dependencies=[_OPS])
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
    min_balance: Decimal | None = Field(default=None, ge=0)


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
    min_balance: Decimal | None = Field(default=None, ge=0)
    is_active: bool | None = None


@router.get("/strategies", dependencies=[_CLIENTS_READ_OR_STRATEGY_READ])
def admin_list_strategies(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    # Broader than other strategy routes on purpose: the Clients tab's grant-
    # entitlement picker needs this list too (ops/finance context, not editing).
    return marketplace.list_catalog(db)


@router.post("/strategies", status_code=status.HTTP_201_CREATED, dependencies=[_STRATEGY])
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
            min_balance=body.min_balance,
        ),
    )


@router.patch("/strategies/{strategy_id}", dependencies=[_STRATEGY])
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


@router.get("/strategies/{strategy_id}/alert-config", dependencies=[_STRATEGY_READ])
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


@router.get("/alerts", dependencies=[_STRATEGY_READ])
def admin_list_alerts(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return alerts.admin_list_alerts(db)


@router.post("/alerts", status_code=status.HTTP_201_CREATED, dependencies=[_STRATEGY])
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


@router.patch("/alerts/{alert_id}", dependencies=[_STRATEGY])
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


@router.get("/alerts/{alert_id}/changelog", dependencies=[_STRATEGY_READ])
def admin_alert_changelog(alert_id: str, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return alerts.admin_get_alert_changelog(db, alert_id)


@router.patch("/strategies/{strategy_id}/alerts", dependencies=[_STRATEGY])
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


@router.post("/assignments", status_code=status.HTTP_201_CREATED, dependencies=[_FINANCE])
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


@router.patch("/assignments/{assignment_id}", dependencies=[_FINANCE])
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


# --------------------------------------------------------------------------
# Payment-proof (UTR) review for paid subscription packages
# --------------------------------------------------------------------------


class RejectPaymentSubmissionRequest(BaseModel):
    reason: str | None = None


@router.get("/payment-submissions", dependencies=[_FINANCE_READ])
def admin_payment_submissions(
    status: str | None = None, db: Session = Depends(get_db)
) -> list[dict[str, Any]]:
    return payments.admin_list_payment_submissions(db, status=status)


@router.post("/payment-submissions/{submission_id}/approve", dependencies=[_FINANCE])
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


@router.post("/payment-submissions/{submission_id}/reject", dependencies=[_FINANCE])
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


# --------------------------------------------------------------------------
# Admin team management (invite/promote, edit roles, deactivate) - the whole
# surface is SUPER_ADMIN-only, unlike everything else in this file.
# --------------------------------------------------------------------------

_ROLE_LABELS = {
    UserRole.SUPER_ADMIN: "Super Admin",
    UserRole.OPERATIONS_ADMIN: "Operations Admin",
    UserRole.STRATEGY_ADMIN: "Strategy Admin",
    UserRole.FINANCE_ADMIN: "Finance Admin",
    UserRole.AUDITOR: "Auditor",
}


def _role_labels(roles: list[UserRole]) -> list[str]:
    return [_ROLE_LABELS.get(r, r.value) for r in roles]


class InviteAdminRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    display_name: str = Field(min_length=1, max_length=120)
    roles: list[UserRole] = Field(min_length=1)
    # Set by the frontend's confirm step after a 409 "existing client" warning
    # (see ConfirmationRequiredError) - false on the first attempt.
    confirm: bool = False


class SetUserRolesRequest(BaseModel):
    roles: list[UserRole] = Field(min_length=1)


@router.post("/invites", status_code=status.HTTP_201_CREATED, dependencies=[_SUPER])
def admin_invite(
    body: InviteAdminRequest,
    db: Session = Depends(get_db),
    claims: Claims = Depends(current_claims),
    sender: EmailSender = Depends(get_email_sender),
) -> dict[str, Any]:
    try:
        user, raw_token = admin_accounts.invite_or_update_admin(
            db,
            email=body.email,
            display_name=body.display_name,
            roles=set(body.roles),
            invited_by=claims.subject,
            confirm=body.confirm,
        )
    except admin_accounts.ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except admin_accounts.ConfirmationRequiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": str(exc),
                "requires_confirmation": True,
                "existing": {
                    "display_name": exc.display_name,
                    "role": exc.role,
                    "extra_roles": exc.extra_roles,
                    "subscription_package": exc.subscription_package,
                    "is_active": exc.is_active,
                },
            },
        ) from exc

    labels = _role_labels(body.roles)
    if raw_token is not None:
        invite_url = f"{get_settings().frontend_base_url}/reset-password?token={raw_token}"
        notifications.send_admin_invite_email(
            sender,
            to=user.email,
            display_name=user.display_name,
            invite_url=invite_url,
            role_labels=labels,
        )
    else:
        notifications.send_admin_roles_updated_email(
            sender, to=user.email, display_name=user.display_name, role_labels=labels
        )
    return {
        "id": str(user.id),
        "email": user.email,
        "display_name": user.display_name,
        "invited": raw_token is not None,
    }


@router.patch("/users/{user_id}/roles", dependencies=[_SUPER])
def admin_set_user_roles(
    user_id: str,
    body: SetUserRolesRequest,
    db: Session = Depends(get_db),
    sender: EmailSender = Depends(get_email_sender),
) -> dict[str, Any]:
    try:
        user = admin_accounts.set_user_roles(db, user_id, set(body.roles))
    except admin_accounts.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except admin_accounts.ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    notifications.send_admin_roles_updated_email(
        sender, to=user.email, display_name=user.display_name, role_labels=_role_labels(body.roles)
    )
    return {"id": str(user.id), "role": user.role}


@router.post("/users/{user_id}/deactivate", dependencies=[_SUPER])
def admin_deactivate_user(
    user_id: str, db: Session = Depends(get_db), claims: Claims = Depends(current_claims)
) -> dict[str, Any]:
    try:
        user = admin_accounts.deactivate_user(
            db, actor_user_id=claims.subject, target_user_id=user_id
        )
    except admin_accounts.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except admin_accounts.ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"id": str(user.id), "is_active": user.is_active}


@router.post("/users/{user_id}/reactivate", dependencies=[_SUPER])
def admin_reactivate_user(user_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        user = admin_accounts.reactivate_user(db, user_id)
    except admin_accounts.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return {"id": str(user.id), "is_active": user.is_active}


@router.delete("/users/{user_id}", dependencies=[_SUPER])
def admin_delete_user(
    user_id: str, db: Session = Depends(get_db), claims: Claims = Depends(current_claims)
) -> Response:
    try:
        admin_accounts.delete_user(db, actor_user_id=claims.subject, target_user_id=user_id)
    except admin_accounts.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except admin_accounts.ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/users/{user_id}/resend-invite", dependencies=[_SUPER])
def admin_resend_invite(
    user_id: str,
    db: Session = Depends(get_db),
    claims: Claims = Depends(current_claims),
    sender: EmailSender = Depends(get_email_sender),
) -> dict[str, Any]:
    try:
        user, raw_token = admin_accounts.resend_invite(db, user_id, invited_by=claims.subject)
    except admin_accounts.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except admin_accounts.ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    extra = admin_accounts.extra_roles_for(db, user.id)
    labels = _role_labels([UserRole(user.role), *[UserRole(r) for r in extra]])
    invite_url = f"{get_settings().frontend_base_url}/reset-password?token={raw_token}"
    notifications.send_admin_invite_email(
        sender, to=user.email, display_name=user.display_name, invite_url=invite_url, role_labels=labels
    )
    return {"id": str(user.id), "resent": True}
