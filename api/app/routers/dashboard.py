"""Dashboard read APIs. Both roles; USER sees only its own executions."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from protrix_contracts.db.models import RiskProfile, TradingControl, User
from sqlalchemy.orm import Session

from app.db import get_db
from app.identity import Claims
from app.security import current_claims
from app.services import read_models

router = APIRouter(prefix="/api/v1", tags=["dashboard"])


def _ensure_user(db: Session, claims: Claims) -> User:
    """Provision an Auth0-derived local user on their first API request."""
    try:
        user_id = UUID(claims.subject)
    except ValueError as exc:
        raise ValueError("identity provider returned an invalid internal subject") from exc
    user = db.get(User, user_id)
    if user is None:
        user = User(
            id=user_id,
            email=claims.email,
            display_name=claims.display_name,
            role=claims.role.value,
            is_active=True,
        )
        db.add(user)
        # New identity users start with restrictive risk controls. An admin can
        # later tune these through the existing risk-management workflow.
        db.add_all(
            [
                TradingControl(user_id=user_id),
                RiskProfile(
                    user_id=user_id,
                    max_lot=Decimal("0.01"),
                    max_open_trades=1,
                    max_daily_loss=Decimal("100.00"),
                    allowed_symbols=["XAUUSD"],
                ),
            ]
        )
        db.flush()
    return user


@router.get("/me")
def me(db: Session = Depends(get_db), claims: Claims = Depends(current_claims)) -> dict[str, Any]:
    _ensure_user(db, claims)
    return {
        "subject": claims.subject,
        "role": claims.role.value,
        "display_name": claims.display_name,
        "email": claims.email,
        "issued_at": claims.issued_at.isoformat(),
        "expires_at": claims.expires_at.isoformat(),
    }


@router.get("/signals")
def signals(
    db: Session = Depends(get_db),
    claims: Claims = Depends(current_claims),
) -> list[dict[str, Any]]:
    return read_models.list_signals(db, viewer_subject=claims.subject, viewer_role=claims.role)


@router.get("/executions")
def executions(
    db: Session = Depends(get_db),
    claims: Claims = Depends(current_claims),
) -> list[dict[str, Any]]:
    return read_models.list_executions(db, viewer_subject=claims.subject, viewer_role=claims.role)
