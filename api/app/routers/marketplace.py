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
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.identity import Claims
from app.security import current_claims
from app.services import marketplace, mt5_connection

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
    multiplier: Literal[1, 2, 3]
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
    multiplier: Literal[1, 2, 3]


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
    db: Session = Depends(get_db), claims: Claims = Depends(current_claims)
) -> dict[str, Any]:
    try:
        return mt5_connection.check_connection(db, claims.subject)
    except mt5_connection.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.delete("/me/mt5-connection")
def disconnect_my_mt5_connection(
    db: Session = Depends(get_db), claims: Claims = Depends(current_claims)
) -> Response:
    try:
        mt5_connection.disconnect_my_connection(db, claims.subject)
    except mt5_connection.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
