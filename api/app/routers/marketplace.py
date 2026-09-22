"""GET /api/v1/strategies, /api/v1/me/assignments - client-facing catalog
browse + multiplier selection (PRD 4.1 steps 4-6, 7).

Any authenticated role can browse. Activation itself is admin-granted for
MVP (docs/FULL-BUILD-PLAN.md decision #4) via POST /api/v1/admin/assignments
- there is no self-service "buy" endpoint here. What a client *can* do
self-service is choose their multiplier within whatever bounds the admin
granted, with an effective-lot preview before saving.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.identity import Claims
from app.security import current_claims
from app.services import marketplace, metaapi_client, mt5_connection

router = APIRouter(prefix="/api/v1", tags=["marketplace"])


@router.get("/strategies")
def browse_strategies(
    db: Session = Depends(get_db),
    claims: Claims = Depends(current_claims),  # noqa: ARG001
) -> list[dict[str, Any]]:
    return marketplace.list_catalog(db, active_only=True)


@router.get("/me/assignments")
def my_assignments(
    db: Session = Depends(get_db), claims: Claims = Depends(current_claims)
) -> list[dict[str, Any]]:
    return marketplace.list_my_assignments(db, claims.subject)


class MultiplierPreviewRequest(BaseModel):
    master_lot: Decimal
    multiplier: Literal[1, 2, 3, 5, 10, 20]
    multiplier_min: Decimal
    multiplier_max: Decimal


@router.post("/me/assignments/preview-lot")
def preview_lot(body: MultiplierPreviewRequest) -> dict[str, str]:
    """Stateless preview - lets the client see the effective lot for a
    multiplier choice before committing it with set_multiplier below."""
    lot = marketplace.preview_effective_lot(
        master_lot=body.master_lot,
        multiplier=Decimal(body.multiplier),
        multiplier_min=body.multiplier_min,
        multiplier_max=body.multiplier_max,
    )
    return {"effective_lot": format(lot, "f")}


class SetMultiplierRequest(BaseModel):
    multiplier: Literal[1, 2, 3, 5, 10, 20]


@router.patch("/me/assignments/{assignment_id}/multiplier")
def set_multiplier(
    assignment_id: str,
    body: SetMultiplierRequest,
    db: Session = Depends(get_db),
    claims: Claims = Depends(current_claims),
) -> dict[str, Any]:
    try:
        return marketplace.set_my_multiplier(
            db,
            user_id=claims.subject,
            assignment_id=assignment_id,
            multiplier=Decimal(body.multiplier),
        )
    except marketplace.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except marketplace.ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.post("/me/assignments/{assignment_id}/confirm-start")
def confirm_start(
    assignment_id: str, db: Session = Depends(get_db), claims: Claims = Depends(current_claims)
) -> dict[str, Any]:
    """Setup Wizard step 3 - the client's explicit, un-skippable risk-disclosure
    confirmation. Only this call can move a SETUP_INCOMPLETE assignment to
    ACTIVE (see marketplace.confirm_start for the enforced preconditions)."""
    try:
        return marketplace.confirm_start(db, user_id=claims.subject, assignment_id=assignment_id)
    except marketplace.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except marketplace.ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


# --------------------------------------------------------------------------
# MT5 connection (PRD 4.1 steps 2-3, 5.2)
# --------------------------------------------------------------------------


class SetMt5ConnectionRequest(BaseModel):
    broker_server: str
    login: str


@router.get("/me/mt5-connection")
def get_my_mt5_connection(
    db: Session = Depends(get_db), claims: Claims = Depends(current_claims)
) -> dict[str, Any] | None:
    return mt5_connection.get_my_connection(db, claims.subject)


@router.get("/me/mt5-connection/balance")
def get_my_mt5_balance(
    db: Session = Depends(get_db),
    claims: Claims = Depends(current_claims),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    return mt5_connection.get_my_live_balance(
        db, claims.subject, metaapi_token=settings.metaapi_token.get_secret_value()
    )


@router.put("/me/mt5-connection")
def set_my_mt5_connection(
    body: SetMt5ConnectionRequest,
    db: Session = Depends(get_db),
    claims: Claims = Depends(current_claims),
) -> dict[str, Any]:
    return mt5_connection.set_my_connection(
        db, user_id=claims.subject, broker_server=body.broker_server, login=body.login
    )


@router.post("/me/mt5-connection/check")
def check_my_mt5_connection(
    db: Session = Depends(get_db),
    claims: Claims = Depends(current_claims),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    try:
        return mt5_connection.check_connection(
            db, claims.subject, metaapi_token=settings.metaapi_token.get_secret_value()
        )
    except mt5_connection.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/me/mt5-connection/metaapi-link")
def start_my_metaapi_link(
    db: Session = Depends(get_db),
    claims: Claims = Depends(current_claims),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Real, self-service MetaApi onboarding - returns a link the client
    visits to enter their MT5 login/password directly with MetaApi. Nothing
    ProTrixPlus (or an admin) ever sees."""
    try:
        return mt5_connection.start_self_service_link(
            db,
            claims.subject,
            metaapi_token=settings.metaapi_token.get_secret_value(),
            default_region=settings.metaapi_default_region,
        )
    except mt5_connection.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except mt5_connection.MetaApiNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except metaapi_client.MetaApiError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


class ConnectMt5WithCredentialsRequest(BaseModel):
    password: str = Field(min_length=1)


@router.post("/me/mt5-connection/connect")
def connect_my_mt5_with_credentials(
    body: ConnectMt5WithCredentialsRequest,
    db: Session = Depends(get_db),
    claims: Claims = Depends(current_claims),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Direct-entry MT5 onboarding - the client's real MT5 password is
    forwarded straight to MetaApi in the account-creation call and never
    stored or logged on our side (see mt5_connection.connect_with_credentials)."""
    try:
        return mt5_connection.connect_with_credentials(
            db,
            claims.subject,
            metaapi_token=settings.metaapi_token.get_secret_value(),
            default_region=settings.metaapi_default_region,
            password=body.password,
        )
    except mt5_connection.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except mt5_connection.MetaApiNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except metaapi_client.MetaApiError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.delete("/me/mt5-connection")
def disconnect_my_mt5_connection(
    db: Session = Depends(get_db), claims: Claims = Depends(current_claims)
) -> Response:
    try:
        mt5_connection.disconnect_my_connection(db, claims.subject)
    except mt5_connection.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
