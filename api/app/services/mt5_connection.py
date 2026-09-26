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

from protrix_contracts.db.models import AuditEvent, Mt5Connection, Mt5ConnectionStatus, User
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.services import metaapi_client


class NotFoundError(Exception):
    pass


class MetaApiNotConfiguredError(Exception):
    pass


class ChargeConfirmationRequiredError(Exception):
    """Raised instead of silently provisioning a new, separately-billed
    MetaApi account - the caller must retry with ``confirm_charge=True``.
    A real incident: test runs (and, before this, nothing at all) could
    trigger real account creation with no explicit "yes, charge this"
    step anywhere - this is enforced here, server-side, so no caller
    (a UI button today, a direct API call, or some future button that
    forgets to check first) can ever create a billable account by
    accident. The client-facing preview (would_create_new_account) exists
    so a UI can warn *before* hitting this wall, but this is the real gate."""

    pass


def pay_mt5_setup_fee(session: Session, user_id: str) -> dict[str, Any]:
    """Demo-only "payment" for the one-time MT5 account setup fee -
    self_subscribe requires this before a client can request any strategy.
    No real payment processor is wired in yet; this just flips the flag and
    records an audit event, the same honest-placeholder shape as every
    other manual-review payment path in this codebase. Idempotent: paying
    twice is a no-op, not an error, so a page refresh/double-click never
    breaks anything - but the caller can check the returned
    ``already_paid`` to avoid double-charging a real processor later.
    """
    user = session.get(User, uuid.UUID(user_id))
    if user is None:
        raise NotFoundError(f"user {user_id} not found")

    already_paid = user.mt5_setup_fee_paid
    if not already_paid:
        user.mt5_setup_fee_paid = True
        session.add(
            AuditEvent(
                event_type="user.mt5_setup_fee_paid",
                entity_type="user",
                entity_id=str(user.id),
                actor=user_id,
                data={"demo_payment": True},
            )
        )
        session.commit()

    return {"mt5_setup_fee_paid": True, "already_paid": already_paid}


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
    session: Session,
    user_id: str,
    *,
    metaapi_token: str,
    default_region: str,
    confirm_charge: bool = False,
) -> dict[str, Any]:
    """Real, self-service MetaApi onboarding: the client never types their
    MT5 password into ProTrixPlus, or hands it to an admin. If this
    connection doesn't have a MetaApi account yet, create one with no
    login/password (MetaApi supports this explicitly - the client supplies
    credentials later, directly to MetaApi). Then generate a fresh
    configuration link either way - safe to call again if the first link
    expired or the client wants to re-enter their password.

    Provisioning a brand new account is real money - never done silently.
    If no existing account can be reused, this raises
    ChargeConfirmationRequiredError unless the caller already passed
    ``confirm_charge=True`` (see would_create_new_account for the preview a
    UI should call first to decide whether to even ask).
    """
    conn = session.scalar(select(Mt5Connection).where(Mt5Connection.user_id == uuid.UUID(user_id)))
    if conn is None:
        raise NotFoundError("set your broker server first")
    if not metaapi_token:
        raise MetaApiNotConfiguredError("MetaApi is not configured on this deployment")

    if not conn.metaapi_account_id:
        found_id = metaapi_client.find_account_id(
            token=metaapi_token,
            login=conn.login,
            server=conn.broker_server,
            prefer_name=f"protrixplus-{user_id}",
        )
        if found_id:
            # Found an account soft-disconnected (undeployed) earlier - wake
            # it back up. Safe no-op if it was already deployed.
            metaapi_client.deploy_account(token=metaapi_token, account_id=found_id)
            conn.metaapi_account_id = found_id
        else:
            if not confirm_charge:
                raise ChargeConfirmationRequiredError(
                    "this provisions a new, separately-billed MetaApi account - "
                    "retry with confirm_charge=true to proceed"
                )
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


def would_create_new_account(
    session: Session, user_id: str, *, metaapi_token: str
) -> dict[str, Any]:
    """Read-only preview of what connect_with_credentials is about to do -
    so the client can be warned specifically when a NEW, separately-billed
    MetaApi account is about to be provisioned, and not bothered with that
    warning when reconnecting/reusing an already-provisioned one (e.g. a
    soft-disconnected account being redeployed, or a broker login someone
    else at ProTrixPlus already has an account for). Mirrors
    connect_with_credentials' own dedup check exactly, without actually
    creating or deploying anything.
    """
    conn = session.scalar(select(Mt5Connection).where(Mt5Connection.user_id == uuid.UUID(user_id)))
    if conn is None or not conn.login or not conn.broker_server:
        raise NotFoundError("set your broker server and MT5 login first")
    if not metaapi_token:
        raise MetaApiNotConfiguredError("MetaApi is not configured on this deployment")

    if conn.metaapi_account_id:
        return {"will_create_new_account": False}

    found_id = metaapi_client.find_account_id(
        token=metaapi_token,
        login=conn.login,
        server=conn.broker_server,
        prefer_name=f"protrixplus-{user_id}",
    )
    return {"will_create_new_account": found_id is None}


def connect_with_credentials(
    session: Session,
    user_id: str,
    *,
    metaapi_token: str,
    default_region: str,
    password: str,
    confirm_charge: bool = False,
) -> dict[str, Any]:
    """Direct-entry MT5 onboarding: the client types their real MT5 password
    into ProTrixPlus, and it's passed straight through to MetaApi in the
    account-creation request - never written to the database (no password
    column exists on Mt5Connection), never logged (httpx's default request
    logging only records method/URL/status, never the request body), and
    never held longer than this one function call.

    Provisioning a brand new account is real money - never done silently.
    If no existing account can be reused, this raises
    ChargeConfirmationRequiredError unless the caller already passed
    ``confirm_charge=True`` (see would_create_new_account for the preview a
    UI should call first to decide whether to even ask).
    """
    conn = session.scalar(select(Mt5Connection).where(Mt5Connection.user_id == uuid.UUID(user_id)))
    if conn is None:
        raise NotFoundError("set your broker server and MT5 login first")
    if not conn.login or not conn.broker_server:
        raise NotFoundError("set your broker server and MT5 login first")
    if not metaapi_token:
        raise MetaApiNotConfiguredError("MetaApi is not configured on this deployment")

    if not conn.metaapi_account_id:
        found_id = metaapi_client.find_account_id(
            token=metaapi_token,
            login=conn.login,
            server=conn.broker_server,
            prefer_name=f"protrixplus-{user_id}",
        )
        if found_id:
            # Found an account soft-disconnected (undeployed) earlier - wake
            # it back up. Safe no-op if it was already deployed.
            metaapi_client.deploy_account(token=metaapi_token, account_id=found_id)
            conn.metaapi_account_id = found_id
        else:
            if not confirm_charge:
                raise ChargeConfirmationRequiredError(
                    "this provisions a new, separately-billed MetaApi account - "
                    "retry with confirm_charge=true to proceed"
                )
            account = metaapi_client.create_account(
                token=metaapi_token,
                name=f"protrixplus-{user_id}",
                server=conn.broker_server,
                region=conn.metaapi_region or default_region,
                magic=0,
                login=conn.login,
                password=password,
            )
            conn.metaapi_account_id = str(account["id"])
        conn.metaapi_region = conn.metaapi_region or default_region
        session.commit()
        session.refresh(conn)

    return check_connection(session, user_id, metaapi_token=metaapi_token)


def disconnect_my_connection(
    session: Session, user_id: str, *, metaapi_token: str = ""
) -> dict[str, Any]:
    """A "soft disconnect": detaching locally used to be the whole story,
    leaving the real MetaApi account (a separately-billed resource) running
    forever with nothing in our own database still pointing at it - the
    same kind of orphan this session found and cleaned up by hand. Now
    best-effort *undeploys* it on MetaApi too - stops the running cloud
    trading terminal (what's actually billed for ongoing use) without
    deleting the account itself, so reconnecting the same broker login
    later (via find_account_id + deploy_account) redeploys this exact
    account for free instead of provisioning - and re-billing for - a new
    one. Skips the undeploy if another user's connection still references
    the exact same account id (possible since connect_with_credentials/
    start_self_service_link reuse an existing account for a shared broker
    login - undeploying it out from under a still-active different user
    would be a real regression, not a cleanup). A remote failure never
    blocks the local disconnect - the user must always be able to detach on
    our side regardless of MetaApi's state - it's just reported back
    instead of silently swallowed.
    """
    conn = session.scalar(select(Mt5Connection).where(Mt5Connection.user_id == uuid.UUID(user_id)))
    if conn is None:
        raise NotFoundError("no MT5 connection configured yet")

    metaapi_account_id = conn.metaapi_account_id
    metaapi_undeployed = False
    metaapi_error: str | None = None

    if metaapi_account_id and metaapi_token:
        shared_with_another_user = session.scalar(
            select(Mt5Connection).where(
                Mt5Connection.metaapi_account_id == metaapi_account_id,
                Mt5Connection.user_id != uuid.UUID(user_id),
            )
        )
        if shared_with_another_user is not None:
            metaapi_error = (
                "not undeployed on MetaApi - this account is still used by another connection"
            )
        else:
            try:
                metaapi_client.undeploy_account(token=metaapi_token, account_id=metaapi_account_id)
                metaapi_undeployed = True
            except metaapi_client.MetaApiError as exc:
                metaapi_error = str(exc)

    session.delete(conn)
    session.commit()
    return {"metaapi_account_undeployed": metaapi_undeployed, "metaapi_error": metaapi_error}


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
