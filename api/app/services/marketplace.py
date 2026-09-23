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
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from protrix_contracts.db.models import (
    AssignmentStatus,
    AuditEvent,
    Mt5Connection,
    Mt5ConnectionStatus,
    PaymentStatus,
    Strategy,
    StrategyAssignment,
    User,
)
from protrix_contracts.money import compute_lot
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.services import mt5_connection

DEFAULT_MULTIPLIER_MIN = Decimal("1")
DEFAULT_MULTIPLIER_MAX = Decimal("3")
# A client picks any whole-number multiplier in this global range via the
# marketplace slider - narrowed further per-assignment by the admin-set
# multiplier_min/multiplier_max risk cap (checked separately below).
MIN_CLIENT_MULTIPLIER = Decimal("1")
MAX_CLIENT_MULTIPLIER = Decimal("100")


class NotFoundError(Exception):
    pass


class ValidationError(Exception):
    pass


def _strategy_dict(s: Strategy) -> dict[str, Any]:
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
        "min_balance": format(s.min_balance, "f") if s.min_balance is not None else None,
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
    min_balance: Decimal | None = None


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
        min_balance=body.min_balance,
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
        "min_balance",
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


def list_catalog(session: Session, *, active_only: bool = False) -> list[dict[str, Any]]:
    stmt = select(Strategy).order_by(Strategy.created_at)
    if active_only:
        stmt = stmt.where(Strategy.is_active.is_(True))
    return [_strategy_dict(s) for s in session.scalars(stmt).all()]


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
            "signal_id": "{{strategy.order.id}}-{{timenow}}",
            "event_time_utc": "{{timenow}}",
            "action": "{{strategy.order.action}}",
            "symbol": "{{ticker}}",
            "timeframe": "{{interval}}",
        },
        "note": (
            "Paste alert_message_template into the TradingView alert's Message "
            "box (TradingView fills in the {{...}} placeholders when it fires). "
            "Set the Webhook URL to your deployment's public host + "
            "webhook_path_template, with <your-webhook-secret> replaced by the "
            "real PROTRIX_TRADINGVIEW_WEBHOOK_SECRET value from infra/.env - "
            "never share that value outside your own deployment config."
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
    if (
        multiplier != multiplier.to_integral_value()
        or multiplier < MIN_CLIENT_MULTIPLIER
        or multiplier > MAX_CLIENT_MULTIPLIER
    ):
        raise ValidationError(
            f"multiplier must be a whole number between {MIN_CLIENT_MULTIPLIER} and "
            f"{MAX_CLIENT_MULTIPLIER}"
        )

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


def confirm_start(
    session: Session, *, user_id: str, assignment_id: str, metaapi_token: str = ""
) -> dict[str, Any]:
    """Setup Wizard step 3: the client's explicit "Start" confirmation.

    This is the ONLY place a SETUP_INCOMPLETE assignment can become ACTIVE -
    an admin grant never sets ACTIVE directly (see admin_grant_entitlement).
    Preconditions are enforced here, server-side, not just by disabling a
    button in the UI: the assignment must actually be awaiting setup, the
    client's MT5 connection must actually be CONNECTED (real, via MetaApi -
    see mt5_connection.check_connection), never assumed, and - if the
    strategy declares a min_balance - the account's real balance must meet
    it. Balance is only ever enforced when it's actually known (MetaApi
    reachable and account attached); an unverifiable balance never blocks
    activation, matching mt5_connection's "never fabricate a result"
    philosophy - it's surfaced as a warning client-side instead.
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

    if strategy.min_balance is not None:
        live_balance = mt5_connection.get_my_live_balance(
            session, user_id, metaapi_token=metaapi_token
        )
        balance = live_balance.get("balance")
        if (
            live_balance.get("available")
            and balance is not None
            and Decimal(str(balance)) < strategy.min_balance
        ):
            raise ValidationError(
                f"your MT5 account balance ({balance} {live_balance.get('currency', '')}) "
                f"is below the {strategy.min_balance} minimum required for "
                f"'{strategy.name}' to work - fund your account before starting"
            )

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
