"""Strategy catalog + entitlement management (PRD 4.1, 4.3, 5.3, 5.8).

Two audiences:
* Admin: create/edit strategy catalog entries, ON/OFF, grant/revoke/override
  a client's entitlement.
* Client: browse the catalog, see own assignments, pick an allowed
  multiplier with an effective-lot preview before saving.

Sizing preview reuses ``protrix_contracts.money.compute_lot`` - the exact
same formula the worker uses for real execution, so a client never sees a
preview number that wouldn't match what actually gets traded.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from protrix_contracts.db.models import (
    AssignmentStatus,
    AuditEvent,
    Mt5Connection,
    Mt5ConnectionStatus,
    PaymentStatus,
    Signal,
    Strategy,
    StrategyAssignment,
    User,
)
from protrix_contracts.money import compute_lot
from sqlalchemy import func, select
from sqlalchemy.orm import Session

DEFAULT_MULTIPLIER_MIN = Decimal("1")
DEFAULT_MULTIPLIER_MAX = Decimal("3")
ALLOWED_CLIENT_MULTIPLIERS = (
    Decimal("1"),
    Decimal("2"),
    Decimal("3"),
    Decimal("5"),
    Decimal("10"),
    Decimal("20"),
)

# A strategy is shown as "connected" while TradingView is actively firing its
# alert; once nothing has arrived for this long we call it "disconnected" -
# e.g. the admin/user deleted the alert on the TradingView side, which we
# have no direct way to detect (TradingView has no alert-management API, see
# app/routers/webhook.py's docstring - this is a one-way inbound push only).
SIGNAL_IDLE_THRESHOLD = timedelta(hours=24)


class NotFoundError(Exception):
    pass


class ValidationError(Exception):
    pass


def _strategy_dict(s: Strategy, *, last_signal_at: datetime | None = None) -> dict[str, Any]:
    connected = last_signal_at is not None and (
        datetime.now(UTC) - last_signal_at <= SIGNAL_IDLE_THRESHOLD
    )
    return {
        "id": str(s.id),
        "strategy_key": s.strategy_key,
        "strategy_version": s.strategy_version,
        "name": s.name,
        "description": s.description,
        "symbol": s.symbol,
        "timeframe": s.timeframe,
        "price": format(s.price, "f") if s.price is not None else None,
        "profit_share_percent": (
            format(s.profit_share_percent, "f") if s.profit_share_percent is not None else None
        ),
        "base_lot": format(s.base_lot, "f") if s.base_lot is not None else None,
        "win_rate": format(s.win_rate, "f") if s.win_rate is not None else None,
        "max_drawdown": format(s.max_drawdown, "f") if s.max_drawdown is not None else None,
        "description_short": s.description_short,
        "is_active": s.is_active,
        "is_archived": s.is_archived,
        "last_signal_at": last_signal_at.isoformat() if last_signal_at is not None else None,
        "signal_status": "connected" if connected else "disconnected",
    }


def _assignment_dict(a: StrategyAssignment, strategy: Strategy) -> dict[str, Any]:
    effective_lot = compute_lot(
        master_lot=a.master_lot,
        multiplier=a.multiplier,
        multiplier_min=a.multiplier_min,
        multiplier_max=a.multiplier_max,
    )
    return {
        "id": str(a.id),
        "strategy_id": str(a.strategy_id),
        "strategy_key": strategy.strategy_key,
        "strategy_name": strategy.name,
        "master_lot": format(a.master_lot, "f"),
        "multiplier": format(a.multiplier, "f"),
        "multiplier_min": format(a.multiplier_min, "f"),
        "multiplier_max": format(a.multiplier_max, "f"),
        "effective_lot": format(effective_lot, "f"),
        "status": a.status,
        "payment_status": a.payment_status,
        "purchased_at": a.purchased_at.isoformat() if a.purchased_at else None,
        "expires_at": a.expires_at.isoformat() if a.expires_at else None,
        "confirmed_risk_disclosure": a.confirmed_risk_disclosure,
        "activated_at": a.activated_at.isoformat() if a.activated_at else None,
    }


# --------------------------------------------------------------------------
# Admin: strategy catalog
# --------------------------------------------------------------------------


@dataclass
class StrategyCatalogInput:
    strategy_key: str
    strategy_version: str
    name: str
    description: str | None = None
    symbol: str | None = None
    timeframe: str | None = None
    price: Decimal | None = None
    profit_share_percent: Decimal | None = None
    base_lot: Decimal | None = None
    win_rate: Decimal | None = None
    max_drawdown: Decimal | None = None
    description_short: str | None = None


def admin_create_strategy(session: Session, body: StrategyCatalogInput) -> dict[str, Any]:
    strategy = Strategy(
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
        # New strategies start hidden from clients (see list_catalog's
        # active_only filter) until an admin has priced it and explicitly
        # approved it via admin_update_strategy(is_active=True).
        is_active=False,
    )
    session.add(strategy)
    session.commit()
    session.refresh(strategy)
    return _strategy_dict(strategy)


def admin_update_strategy(
    session: Session, strategy_id: str, *, is_active: bool | None = None, **fields: Any
) -> dict[str, Any]:
    strategy = session.get(Strategy, uuid.UUID(strategy_id))
    if strategy is None:
        raise NotFoundError(f"strategy {strategy_id} not found")

    for field in (
        "name",
        "description",
        "symbol",
        "timeframe",
        "price",
        "profit_share_percent",
        "base_lot",
        "win_rate",
        "max_drawdown",
        "description_short",
    ):
        if field in fields and fields[field] is not None:
            setattr(strategy, field, fields[field])

    if is_active:
        # A strategy only becomes visible to clients (list_catalog's
        # active_only filter) once it's actually priced - don't let it go
        # live with a blank subscription price or profit-share commission.
        if strategy.price is None or strategy.profit_share_percent is None:
            raise ValidationError(
                "set a price and profit-share percent before activating this strategy"
            )
        strategy.is_active = True
    elif is_active is False:
        strategy.is_active = False

    session.commit()
    session.refresh(strategy)
    return _strategy_dict(strategy)


def admin_archive_strategy(session: Session, strategy_id: str, *, actor: str) -> dict[str, Any]:
    """ "Remove from the admin panel" for a strategy with real trade history
    can't be a hard DELETE (strategy_assignments/order_intents FK to it with
    no cascade - see 0008_strategy_archive's migration docstring). Archiving
    hides it from both the admin catalog and the client marketplace
    (list_catalog filters is_archived out by default) while every
    assignment/order-intent/signal referencing it stays intact. Also forces
    is_active off, same as a normal Turn OFF, so it can't keep fanning out
    signals to existing subscribers while hidden."""
    strategy = session.get(Strategy, uuid.UUID(strategy_id))
    if strategy is None:
        raise NotFoundError(f"strategy {strategy_id} not found")

    strategy.is_archived = True
    strategy.is_active = False
    session.add(
        AuditEvent(
            event_type="strategy.archived",
            entity_type="strategy",
            entity_id=str(strategy.id),
            actor=actor,
            data={
                "strategy_key": strategy.strategy_key,
                "strategy_version": strategy.strategy_version,
            },
        )
    )
    session.commit()
    session.refresh(strategy)
    return _strategy_dict(strategy)


def admin_unarchive_strategy(session: Session, strategy_id: str, *, actor: str) -> dict[str, Any]:
    """Reverses admin_archive_strategy. The strategy reappears in the admin
    catalog but stays NOT ENABLED (is_active still False) - admin must
    explicitly re-price/re-approve it, same as any newly created strategy."""
    strategy = session.get(Strategy, uuid.UUID(strategy_id))
    if strategy is None:
        raise NotFoundError(f"strategy {strategy_id} not found")

    strategy.is_archived = False
    session.add(
        AuditEvent(
            event_type="strategy.unarchived",
            entity_type="strategy",
            entity_id=str(strategy.id),
            actor=actor,
            data={
                "strategy_key": strategy.strategy_key,
                "strategy_version": strategy.strategy_version,
            },
        )
    )
    session.commit()
    session.refresh(strategy)
    return _strategy_dict(strategy)


def list_catalog(
    session: Session, *, active_only: bool = False, include_archived: bool = False
) -> list[dict[str, Any]]:
    stmt = select(Strategy).order_by(Strategy.created_at)
    if active_only:
        stmt = stmt.where(Strategy.is_active.is_(True))
    if not include_archived:
        stmt = stmt.where(Strategy.is_archived.is_(False))
    strategies = session.scalars(stmt).all()

    last_signal_rows = session.execute(
        select(
            Signal.strategy_key,
            Signal.strategy_version,
            func.max(Signal.accepted_at),
        ).group_by(Signal.strategy_key, Signal.strategy_version)
    ).all()
    last_signal_by_key = {(row[0], row[1]): row[2] for row in last_signal_rows}

    return [
        _strategy_dict(
            s, last_signal_at=last_signal_by_key.get((s.strategy_key, s.strategy_version))
        )
        for s in strategies
    ]


def list_unmapped_signal_strategies(session: Session) -> list[dict[str, Any]]:
    """Distinct (strategy_key, strategy_version) pairs TradingView has
    actually sent us that don't match any Strategy row yet - i.e. a real
    alert is firing but nobody has created a catalog entry for it. Powers
    the "pick from what's actually arriving" dropdown in the admin Create
    Strategy form, so the admin never has to hand-type a key/version that
    has to match a live signal byte-for-byte."""
    existing = set(session.execute(select(Strategy.strategy_key, Strategy.strategy_version)).all())

    rows = session.execute(
        select(
            Signal.strategy_key,
            Signal.strategy_version,
            Signal.symbol,
            Signal.timeframe,
            Signal.accepted_at,
        ).order_by(Signal.accepted_at.desc())
    ).all()

    unmapped: dict[tuple[str, str], dict[str, Any]] = {}
    for strategy_key, strategy_version, symbol, timeframe, accepted_at in rows:
        key = (strategy_key, strategy_version)
        if key in existing:
            continue
        if key not in unmapped:
            # Rows arrive newest-first, so the first sighting of a key is
            # its most recent signal - that's what we use for symbol/
            # timeframe (a strategy could in principle change these, but
            # the latest signal is the most useful default to prefill).
            unmapped[key] = {
                "strategy_key": strategy_key,
                "strategy_version": strategy_version,
                "symbol": symbol,
                "timeframe": timeframe,
                "first_seen_at": accepted_at,
                "last_seen_at": accepted_at,
                "signal_count": 0,
            }
        entry = unmapped[key]
        entry["signal_count"] += 1
        entry["first_seen_at"] = accepted_at

    return [
        {
            **entry,
            "first_seen_at": entry["first_seen_at"].isoformat(),
            "last_seen_at": entry["last_seen_at"].isoformat(),
        }
        for entry in sorted(unmapped.values(), key=lambda e: e["last_seen_at"], reverse=True)
    ]


def alert_config_for_strategy(session: Session, strategy_id: str) -> dict[str, Any]:
    """PRD 4.3 step 3: what the admin pastes into TradingView's alert config
    to map that alert to this strategy.

    Deliberately never returns the actual webhook secret value - that lives
    only in the deployment's own PROTRIX_TRADINGVIEW_WEBHOOK_SECRET env var,
    never in an API response (see docs/PRODUCTION-READINESS-ISSUES.md #4 on
    why a webhook secret leaking into logs/API responses is a real risk).
    The admin (who has deploy access) fills in <your-webhook-secret>
    themselves from that env var.
    """
    strategy = session.get(Strategy, uuid.UUID(strategy_id))
    if strategy is None:
        raise NotFoundError(f"strategy {strategy_id} not found")

    return {
        "strategy_id": str(strategy.id),
        "webhook_path_template": "/webhook/tradingview/<your-webhook-secret>",
        "alert_message_template": {
            "schema_version": "1.0",
            "strategy_key": strategy.strategy_key,
            "strategy_version": strategy.strategy_version,
            "order_id": "{{strategy.order.id}}",
            "event_time_utc": "{{timenow}}",
            "action": "{{strategy.order.action}}",
            "symbol": "{{ticker}}",
            "timeframe": "{{interval}}",
        },
        "note": (
            "Paste alert_message_template into the TradingView alert's Message "
            "box (TradingView fills in the {{...}} placeholders when it fires). "
            "order_id + event_time_utc are combined server-side into the "
            "signal_id our webhook actually requires - kept as two separate "
            "single-placeholder fields here because TradingView's alert editor "
            "sometimes mis-lints a value with two {{...}} placeholders "
            "concatenated in one string (harmless warning, but this format "
            "avoids it entirely). Set the Webhook URL to your deployment's "
            "public host + webhook_path_template, with <your-webhook-secret> "
            "replaced by the real PROTRIX_TRADINGVIEW_WEBHOOK_SECRET value from "
            "infra/.env - never share that value outside your own deployment "
            "config."
        ),
    }


# --------------------------------------------------------------------------
# Admin: entitlement grant / override / revoke
# --------------------------------------------------------------------------


def admin_grant_entitlement(
    session: Session,
    *,
    user_id: str,
    strategy_id: str,
    master_lot: Decimal,
    multiplier: Decimal = Decimal("1"),
    multiplier_min: Decimal = DEFAULT_MULTIPLIER_MIN,
    multiplier_max: Decimal = DEFAULT_MULTIPLIER_MAX,
    expires_at: datetime | None = None,
) -> dict[str, Any]:
    user = session.get(User, uuid.UUID(user_id))
    strategy = session.get(Strategy, uuid.UUID(strategy_id))
    if user is None:
        raise NotFoundError(f"user {user_id} not found")
    if strategy is None:
        raise NotFoundError(f"strategy {strategy_id} not found")

    existing = session.scalar(
        select(StrategyAssignment).where(
            StrategyAssignment.user_id == user.id, StrategyAssignment.strategy_id == strategy.id
        )
    )
    now = datetime.now(UTC)
    if existing is not None:
        # Deliberately does NOT touch `status`: an admin re-granting (e.g.
        # bumping master_lot) for an already-active client must never
        # silently pause their live trading, and must never reset an
        # in-progress setup back to SETUP_INCOMPLETE either.
        existing.master_lot = master_lot
        existing.multiplier = multiplier
        existing.multiplier_min = multiplier_min
        existing.multiplier_max = multiplier_max
        existing.payment_status = PaymentStatus.GRANTED.value
        existing.purchased_at = now
        existing.expires_at = expires_at
        assignment = existing
    else:
        assignment = StrategyAssignment(
            user_id=user.id,
            strategy_id=strategy.id,
            master_lot=master_lot,
            multiplier=multiplier,
            multiplier_min=multiplier_min,
            multiplier_max=multiplier_max,
            # New grants require the client to complete the setup wizard
            # (sizing + MT5 connection + explicit risk confirmation) before
            # any signal fans out to them - see confirm_start below and
            # worker/app/fanout.py's ACTIVE-only eligibility query.
            status=AssignmentStatus.SETUP_INCOMPLETE.value,
            payment_status=PaymentStatus.GRANTED.value,
            purchased_at=now,
            expires_at=expires_at,
        )
        session.add(assignment)

    session.commit()
    session.refresh(assignment)
    return _assignment_dict(assignment, strategy)


def admin_update_assignment(
    session: Session,
    assignment_id: str,
    *,
    master_lot: Decimal | None = None,
    multiplier_min: Decimal | None = None,
    multiplier_max: Decimal | None = None,
    status: str | None = None,
    payment_status: str | None = None,
    expires_at: datetime | None = ...,  # type: ignore[assignment]  # sentinel: only touch if passed
) -> dict[str, Any]:
    assignment = session.get(StrategyAssignment, uuid.UUID(assignment_id))
    if assignment is None:
        raise NotFoundError(f"assignment {assignment_id} not found")
    strategy = session.get(Strategy, assignment.strategy_id)
    assert strategy is not None  # FK guarantees this

    if master_lot is not None:
        assignment.master_lot = master_lot
    if multiplier_min is not None:
        assignment.multiplier_min = multiplier_min
    if multiplier_max is not None:
        assignment.multiplier_max = multiplier_max
    if status is not None:
        assignment.status = status
    if payment_status is not None:
        assignment.payment_status = payment_status
    if expires_at is not ...:
        assignment.expires_at = expires_at

    # A per-client override must never leave `multiplier` outside the (possibly
    # just-narrowed) bounds - clamp rather than silently invalidate the row.
    if assignment.multiplier < assignment.multiplier_min:
        assignment.multiplier = assignment.multiplier_min
    if assignment.multiplier > assignment.multiplier_max:
        assignment.multiplier = assignment.multiplier_max

    session.commit()
    session.refresh(assignment)
    return _assignment_dict(assignment, strategy)


# --------------------------------------------------------------------------
# Client: browse + own assignments + multiplier selection
# --------------------------------------------------------------------------


def self_subscribe(session: Session, *, user_id: str, strategy_id: str) -> dict[str, Any]:
    """Self-service subscription request: any signed-up client can see and
    request any published strategy immediately - no admin action needed to
    *request* it. The resulting assignment starts PENDING_APPROVAL - visible
    to the client, but locked (no Setup Wizard access) until an admin
    confirms the strategy's subscription price was actually paid and moves
    it to SETUP_INCOMPLETE via admin_approve_subscription. Idempotent -
    returns the existing assignment untouched if the client already has one,
    rather than duplicating or resetting it.
    """
    user = session.get(User, uuid.UUID(user_id))
    strategy = session.get(Strategy, uuid.UUID(strategy_id))
    if user is None:
        raise NotFoundError(f"user {user_id} not found")
    if strategy is None:
        raise NotFoundError(f"strategy {strategy_id} not found")
    if not strategy.is_active:
        raise ValidationError("this strategy isn't published yet")

    existing = session.scalar(
        select(StrategyAssignment).where(
            StrategyAssignment.user_id == user.id, StrategyAssignment.strategy_id == strategy.id
        )
    )
    if existing is not None:
        return _assignment_dict(existing, strategy)

    assignment = StrategyAssignment(
        user_id=user.id,
        strategy_id=strategy.id,
        master_lot=strategy.base_lot or Decimal("1.00"),
        multiplier=Decimal("1"),
        multiplier_min=DEFAULT_MULTIPLIER_MIN,
        multiplier_max=Decimal("20"),
        status=AssignmentStatus.PENDING_APPROVAL.value,
        payment_status=PaymentStatus.GRANTED.value,
        purchased_at=datetime.now(UTC),
    )
    session.add(assignment)
    session.commit()
    session.refresh(assignment)
    return _assignment_dict(assignment, strategy)


def admin_approve_subscription(
    session: Session, assignment_id: str, *, actor: str
) -> dict[str, Any]:
    """Admin confirms the client actually paid for this strategy's
    subscription (out-of-band for MVP - see docs/FULL-BUILD-PLAN.md open
    question #5) and unlocks it: PENDING_APPROVAL -> SETUP_INCOMPLETE, which
    gives the client Setup Wizard access. Only valid from PENDING_APPROVAL -
    an already-approved or active assignment has nothing to approve."""
    assignment = session.get(StrategyAssignment, uuid.UUID(assignment_id))
    if assignment is None:
        raise NotFoundError(f"assignment {assignment_id} not found")
    if assignment.status != AssignmentStatus.PENDING_APPROVAL.value:
        raise ValidationError(
            f"assignment is '{assignment.status}', not awaiting approval - nothing to approve"
        )
    strategy = session.get(Strategy, assignment.strategy_id)
    assert strategy is not None

    assignment.status = AssignmentStatus.SETUP_INCOMPLETE.value
    session.add(
        AuditEvent(
            event_type="assignment.approved",
            entity_type="assignment",
            entity_id=str(assignment.id),
            actor=actor,
            data={"strategy_id": str(strategy.id)},
        )
    )
    session.commit()
    session.refresh(assignment)
    return _assignment_dict(assignment, strategy)


def list_my_assignments(session: Session, user_id: str) -> list[dict[str, Any]]:
    stmt = (
        select(StrategyAssignment, Strategy)
        .join(Strategy, StrategyAssignment.strategy_id == Strategy.id)
        .where(StrategyAssignment.user_id == uuid.UUID(user_id))
        .order_by(StrategyAssignment.created_at)
    )
    return [_assignment_dict(a, s) for a, s in session.execute(stmt).all()]


def preview_effective_lot(
    *, master_lot: Decimal, multiplier: Decimal, multiplier_min: Decimal, multiplier_max: Decimal
) -> Decimal:
    return compute_lot(
        master_lot=master_lot,
        multiplier=multiplier,
        multiplier_min=multiplier_min,
        multiplier_max=multiplier_max,
    )


def set_my_multiplier(
    session: Session, *, user_id: str, assignment_id: str, multiplier: Decimal
) -> dict[str, Any]:
    if multiplier not in ALLOWED_CLIENT_MULTIPLIERS:
        raise ValidationError("multiplier must be one of 1, 2, 3, 5, 10, 20")

    assignment = session.get(StrategyAssignment, uuid.UUID(assignment_id))
    if assignment is None or str(assignment.user_id) != user_id:
        raise NotFoundError(f"assignment {assignment_id} not found")
    if multiplier < assignment.multiplier_min or multiplier > assignment.multiplier_max:
        raise ValidationError(
            f"multiplier {multiplier} is outside your allowed range "
            f"({assignment.multiplier_min}-{assignment.multiplier_max})"
        )

    strategy = session.get(Strategy, assignment.strategy_id)
    assert strategy is not None

    assignment.multiplier = multiplier
    session.commit()
    session.refresh(assignment)
    return _assignment_dict(assignment, strategy)


def confirm_start(session: Session, *, user_id: str, assignment_id: str) -> dict[str, Any]:
    """Setup Wizard step 3: the client's explicit "Start" confirmation.

    This is the ONLY place a SETUP_INCOMPLETE assignment can become ACTIVE -
    an admin grant never sets ACTIVE directly (see admin_grant_entitlement).
    Both preconditions are enforced here, server-side, not just by disabling
    a button in the UI: the assignment must actually be awaiting setup, and
    the client's MT5 connection must actually be CONNECTED (real, via
    MetaApi - see mt5_connection.check_connection), never assumed.
    """
    assignment = session.get(StrategyAssignment, uuid.UUID(assignment_id))
    if assignment is None or str(assignment.user_id) != user_id:
        raise NotFoundError(f"assignment {assignment_id} not found")
    if assignment.status != AssignmentStatus.SETUP_INCOMPLETE.value:
        raise ValidationError(
            f"assignment is '{assignment.status}', not awaiting setup - nothing to confirm"
        )

    connection = session.scalar(
        select(Mt5Connection).where(Mt5Connection.user_id == uuid.UUID(user_id))
    )
    if connection is None or connection.status != Mt5ConnectionStatus.CONNECTED.value:
        raise ValidationError("connect your MT5 account before starting this strategy")

    strategy = session.get(Strategy, assignment.strategy_id)
    assert strategy is not None

    assignment.confirmed_risk_disclosure = True
    assignment.activated_at = datetime.now(UTC)
    assignment.status = AssignmentStatus.ACTIVE.value
    session.add(
        AuditEvent(
            event_type="assignment.activated",
            entity_type="assignment",
            entity_id=str(assignment.id),
            actor=user_id,
            data={"strategy_id": str(strategy.id)},
        )
    )
    session.commit()
    session.refresh(assignment)
    return _assignment_dict(assignment, strategy)
