"""MT5 connection management (PRD 3.1, 4.1 steps 2-3, 5.2).

``check_connection`` is an honest stub: there is no real MetaApi.cloud
integration wired in yet (needs a real API key - see
docs/FULL-BUILD-PLAN.md Phase 3/5 and ADR-001). It always reports PENDING
with a clear reason rather than fabricating a CONNECTED/DISCONNECTED result.
Once real credentials exist, only this one function needs to change - the
schema, endpoints, and status vocabulary are already the real shape.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from protrix_contracts.db.models import Mt5Connection, Mt5ConnectionStatus, User
from sqlalchemy import select
from sqlalchemy.orm import Session


class NotFoundError(Exception):
    pass


def _dict(c: Mt5Connection) -> dict[str, Any]:
    return {
        "id": str(c.id),
        "broker_server": c.broker_server,
        "login": c.login,
        "status": c.status,
        "last_checked_at": c.last_checked_at.isoformat() if c.last_checked_at else None,
        "last_error": c.last_error,
    }


def get_my_connection(session: Session, user_id: str) -> dict[str, Any] | None:
    c = session.scalar(select(Mt5Connection).where(Mt5Connection.user_id == uuid.UUID(user_id)))
    return _dict(c) if c else None


def set_my_connection(
    session: Session, *, user_id: str, broker_server: str, login: str
) -> dict[str, Any]:
    existing = session.scalar(
        select(Mt5Connection).where(Mt5Connection.user_id == uuid.UUID(user_id))
    )
    if existing is not None:
        existing.broker_server = broker_server
        existing.login = login
        existing.status = Mt5ConnectionStatus.NOT_CONFIGURED.value
        existing.last_checked_at = None
        existing.last_error = None
        conn = existing
    else:
        conn = Mt5Connection(
            user_id=uuid.UUID(user_id),
            broker_server=broker_server,
            login=login,
            status=Mt5ConnectionStatus.NOT_CONFIGURED.value,
        )
        session.add(conn)

    session.commit()
    session.refresh(conn)
    return _dict(conn)


def check_connection(session: Session, user_id: str) -> dict[str, Any]:
    """Stub: no real MetaApi wiring exists yet. Always PENDING, never a fake
    CONNECTED. See module docstring."""
    conn = session.scalar(select(Mt5Connection).where(Mt5Connection.user_id == uuid.UUID(user_id)))
    if conn is None:
        raise NotFoundError("no MT5 connection configured yet")

    conn.status = Mt5ConnectionStatus.PENDING.value
    conn.last_checked_at = datetime.now(UTC)
    conn.last_error = (
        "MetaApi.cloud integration not yet configured for this deployment "
        "(no API key wired in) - connection details are stored but not "
        "actually verified against a broker yet."
    )
    session.commit()
    session.refresh(conn)
    return _dict(conn)


def disconnect_my_connection(session: Session, user_id: str) -> None:
    conn = session.scalar(select(Mt5Connection).where(Mt5Connection.user_id == uuid.UUID(user_id)))
    if conn is None:
        raise NotFoundError("no MT5 connection configured yet")
    session.delete(conn)
    session.commit()


def admin_list_connections(session: Session) -> list[dict[str, Any]]:
    stmt = (
        select(Mt5Connection, User)
        .join(User, Mt5Connection.user_id == User.id)
        .order_by(User.display_name)
    )
    out = []
    for c, u in session.execute(stmt).all():
        row = _dict(c)
        row["user_id"] = str(u.id)
        row["user_display_name"] = u.display_name
        out.append(row)
    return out
