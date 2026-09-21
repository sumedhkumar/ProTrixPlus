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

from app.services import metaapi_client


class NotFoundError(Exception):
    pass


class MetaApiNotConfiguredError(Exception):
    pass


def _dict(c: Mt5Connection) -> dict[str, Any]:
    return {
        "id": str(c.id),
        "broker_server": c.broker_server,
        "login": c.login,
        "status": c.status,
        "last_checked_at": c.last_checked_at.isoformat() if c.last_checked_at else None,
        "last_error": c.last_error,
        "metaapi_account_id": c.metaapi_account_id,
        "metaapi_region": c.metaapi_region,
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


def _probe_trading_api(*, metaapi_token: str, region: str | None, account_id: str) -> str | None:
    """CONNECTED (above) only means MetaApi's terminal is logged into the
    broker - a separate fact from whether MetaApi's own regional trading API
    (the host every trade/balance call actually goes through) is reachable
    right now. Those can genuinely diverge during a MetaApi-side regional
    outage: the broker connection stays healthy while every trade call still
    fails. Probing here surfaces that degraded state in `last_error` instead
    of only in worker logs - `status` itself stays CONNECTED (the broker
    connection *is* fine), since flipping it to PENDING/ERROR would
    incorrectly block the setup wizard and existing live clients."""
    if not region:
        return None
    try:
        metaapi_client.get_account_information(
            token=metaapi_token, region=region, account_id=account_id
        )
    except metaapi_client.MetaApiError as exc:
        return (
            "MT5 terminal is connected to your broker, but MetaApi's trading API is "
            f"currently unavailable ({exc}) - trade placement may fail until this clears."
        )
    return None


def check_connection(session: Session, user_id: str, *, metaapi_token: str = "") -> dict[str, Any]:
    """Real check when a MetaApi account is attached; an honest PENDING stub
    (never a fabricated CONNECTED) when it isn't yet."""
    conn = session.scalar(select(Mt5Connection).where(Mt5Connection.user_id == uuid.UUID(user_id)))
    if conn is None:
        raise NotFoundError("no MT5 connection configured yet")

    if conn.metaapi_account_id and metaapi_token:
        try:
            status = metaapi_client.get_account_status(
                token=metaapi_token, account_id=conn.metaapi_account_id
            )
        except metaapi_client.MetaApiError as exc:
            conn.status = Mt5ConnectionStatus.ERROR.value
            conn.last_error = str(exc)
        else:
            connection_status = status.get("connectionStatus")
            if connection_status == "CONNECTED":
                conn.status = Mt5ConnectionStatus.CONNECTED.value
                conn.last_error = _probe_trading_api(
                    metaapi_token=metaapi_token,
                    region=conn.metaapi_region,
                    account_id=conn.metaapi_account_id,
                )
            else:
                conn.status = Mt5ConnectionStatus.PENDING.value
                conn.last_error = (
                    f"MetaApi reports state={status.get('state')}, "
                    f"connectionStatus={connection_status} - waiting for the client to finish "
                    "entering their MT5 login/password via the configuration link."
                )
    else:
        conn.status = Mt5ConnectionStatus.PENDING.value
        conn.last_error = (
            "No MetaApi account attached yet - use 'Connect via MetaApi' to generate a "
            "secure setup link, or an admin can attach an existing account id."
        )

    conn.last_checked_at = datetime.now(UTC)
    session.commit()
    session.refresh(conn)
    return _dict(conn)


def start_self_service_link(
    session: Session, user_id: str, *, metaapi_token: str, default_region: str
) -> dict[str, Any]:
    """Real, self-service MetaApi onboarding: the client never types their
    MT5 password into ProTrixPlus, or hands it to an admin. If this
    connection doesn't have a MetaApi account yet, create one with no
    login/password (MetaApi supports this explicitly - the client supplies
    credentials later, directly to MetaApi). Then generate a fresh
    configuration link either way - safe to call again if the first link
    expired or the client wants to re-enter their password.
    """
    conn = session.scalar(select(Mt5Connection).where(Mt5Connection.user_id == uuid.UUID(user_id)))
    if conn is None:
        raise NotFoundError("set your broker server first")
    if not metaapi_token:
        raise MetaApiNotConfiguredError("MetaApi is not configured on this deployment")

    if not conn.metaapi_account_id:
        account = metaapi_client.create_account(
            token=metaapi_token,
            name=f"protrixplus-{user_id}",
            server=conn.broker_server,
            region=conn.metaapi_region or default_region,
            magic=0,
        )
        conn.metaapi_account_id = str(account["id"])
        conn.metaapi_region = conn.metaapi_region or default_region
        session.commit()
        session.refresh(conn)

    link = metaapi_client.create_configuration_link(
        token=metaapi_token, account_id=conn.metaapi_account_id
    )
    conn.status = Mt5ConnectionStatus.PENDING.value
    conn.last_error = "Waiting for the client to complete setup via the configuration link."
    conn.last_checked_at = datetime.now(UTC)
    session.commit()
    return {"configuration_link": link, "metaapi_account_id": conn.metaapi_account_id}


def disconnect_my_connection(session: Session, user_id: str) -> None:
    conn = session.scalar(select(Mt5Connection).where(Mt5Connection.user_id == uuid.UUID(user_id)))
    if conn is None:
        raise NotFoundError("no MT5 connection configured yet")
    session.delete(conn)
    session.commit()


def get_my_live_balance(session: Session, user_id: str, *, metaapi_token: str) -> dict[str, Any]:
    """Real balance/equity for the caller's own connected account.

    Always returns a dict describing *why* if it can't - never a fabricated
    number. ``available`` is False when there's no connection, no MetaApi
    account attached yet, or MetaApi itself failed/timed out.
    """
    conn = session.scalar(select(Mt5Connection).where(Mt5Connection.user_id == uuid.UUID(user_id)))
    if conn is None or not conn.metaapi_account_id or not conn.metaapi_region:
        return {
            "available": False,
            "reason": "no MetaApi account attached to your MT5 connection yet",
        }

    if not metaapi_token:
        return {"available": False, "reason": "MetaApi is not configured on this deployment"}

    try:
        info = metaapi_client.get_account_information(
            token=metaapi_token, region=conn.metaapi_region, account_id=conn.metaapi_account_id
        )
    except metaapi_client.MetaApiError as exc:
        return {"available": False, "reason": str(exc)}

    return {
        "available": True,
        "balance": info.get("balance"),
        "equity": info.get("equity"),
        "free_margin": info.get("freeMargin"),
        "currency": info.get("currency"),
        "leverage": info.get("leverage"),
        "trade_mode": info.get("type"),
    }


def admin_set_metaapi_account(
    session: Session, connection_id: str, *, metaapi_account_id: str, metaapi_region: str
) -> dict[str, Any]:
    """Attach the MetaApi side of a client's MT5 connection (admin-only -
    these values come from MetaApi's own dashboard after the admin adds the
    client's account there, not from the client)."""
    conn = session.get(Mt5Connection, uuid.UUID(connection_id))
    if conn is None:
        raise NotFoundError(f"mt5 connection {connection_id} not found")
    conn.metaapi_account_id = metaapi_account_id
    conn.metaapi_region = metaapi_region
    session.commit()
    session.refresh(conn)
    return _dict(conn)


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
