"""Super-admin-only read APIs.

The whole router is gated: ``dependencies=[Depends(require_role(SUPER_ADMIN))]``.
A USER token gets 403 on every path here.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from protrix_contracts.db.models import UserRole
from sqlalchemy.orm import Session

from app.db import get_db
from app.security import require_role
from app.services import read_models

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
