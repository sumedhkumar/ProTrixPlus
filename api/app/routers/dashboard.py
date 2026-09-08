"""Dashboard read APIs. Both roles; USER sees only its own executions."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.identity import Claims
from app.security import current_claims
from app.services import read_models

router = APIRouter(prefix="/api/v1", tags=["dashboard"])


@router.get("/me")
def me(claims: Claims = Depends(current_claims)) -> dict[str, Any]:
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
    return read_models.list_signals(db)


@router.get("/executions")
def executions(
    db: Session = Depends(get_db),
    claims: Claims = Depends(current_claims),
) -> list[dict[str, Any]]:
    return read_models.list_executions(db, viewer_subject=claims.subject, viewer_role=claims.role)
