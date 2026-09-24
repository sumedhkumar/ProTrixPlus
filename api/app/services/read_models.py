"""Read models for the dashboard APIs. Stored data only - no live computation."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from protrix_contracts.db.models import (
    Execution,
    Mt5Connection,
    Mt5ConnectionStatus,
    OrderIntent,
    Signal,
    Strategy,
    StrategyAssignment,
    User,
    UserRole,
)
from protrix_contracts.lifecycle import ExecutionState
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.services import admin_accounts


def list_signals(session: Session, *, limit: int = 100) -> list[dict[str, Any]]:
    intent_counts: dict[uuid.UUID, int] = {
        sig_id: count
        for sig_id, count in session.execute(
            select(OrderIntent.signal_id, func.count()).group_by(OrderIntent.signal_id)
        ).all()
    }
    rows = session.scalars(select(Signal).order_by(Signal.accepted_at.desc()).limit(limit)).all()
    return [
        {
            "id": str(s.id),
            "signal_id": s.signal_id,
            "strategy_key": s.strategy_key,
            "strategy_version": s.strategy_version,
            "action": s.action,
            "symbol": s.symbol,
            "timeframe": s.timeframe,
            "payload_hash": s.payload_hash,
            "event_time_utc": s.event_time_utc.isoformat(),
            "accepted_at": s.accepted_at.isoformat(),
            "intent_count": int(intent_counts.get(s.id, 0)),
        }
        for s in rows
    ]


def list_executions(
    session: Session, *, viewer_subject: str, viewer_role: UserRole, limit: int = 200
) -> list[dict[str, Any]]:
    stmt = (
        select(Execution, OrderIntent, Signal, User, Strategy)
        .join(OrderIntent, Execution.order_intent_id == OrderIntent.id)
        .join(Signal, OrderIntent.signal_id == Signal.id)
        .join(User, OrderIntent.user_id == User.id)
        .join(Strategy, OrderIntent.strategy_id == Strategy.id)
        .order_by(Execution.updated_at.desc())
        .limit(limit)
    )
    if viewer_role is UserRole.USER:
        stmt = stmt.where(OrderIntent.user_id == viewer_subject)

    out: list[dict[str, Any]] = []
    for ex, intent, signal, user, strategy in session.execute(stmt).all():
        out.append(
            {
                "id": str(ex.id),
                "signal_id": str(signal.id),
                "signal_ref": signal.signal_id,
                "user_id": str(user.id),
                "user_display_name": user.display_name,
                "strategy_key": strategy.strategy_key,
                "symbol": intent.symbol,
                "action": signal.action,
                "command_target": intent.command_target,
                "computed_lot": format(intent.computed_lot, "f"),
                "adapter": ex.adapter,
                "state": ex.state,
                "last_error": ex.last_error,
                "ticket_id": ex.ticket_id,
                "deal_id": ex.deal_id,
                "reconcile_count": ex.reconcile_count,
                "latency_dispatch_ms": ex.latency_dispatch_ms,
                "latency_ack_ms": ex.latency_ack_ms,
                "latency_fill_ms": ex.latency_fill_ms,
                "entry_price": format(ex.entry_price, "f") if ex.entry_price is not None else None,
                "exit_price": format(ex.exit_price, "f") if ex.exit_price is not None else None,
                "realized_pnl": (
                    format(ex.realized_pnl, "f") if ex.realized_pnl is not None else None
                ),
                "updated_at": ex.updated_at.isoformat(),
            }
        )
    return out


def pnl_summary(session: Session, *, viewer_subject: str, viewer_role: UserRole) -> dict[str, Any]:
    """PRD 5.6: P&L attribution. Realized only - an execution with no
    ``realized_pnl`` yet (position still open, or no real broker fills have
    landed - see docs/FULL-BUILD-PLAN.md Phase 5) simply isn't counted yet,
    never estimated.
    """
    stmt = select(Execution, OrderIntent).join(
        OrderIntent, Execution.order_intent_id == OrderIntent.id
    )
    if viewer_role is UserRole.USER:
        stmt = stmt.where(OrderIntent.user_id == viewer_subject)

    total = Decimal("0")
    realized_count = 0
    attributable_count = 0
    for ex, _intent in session.execute(stmt).all():
        attributable_count += 1
        if ex.realized_pnl is not None:
            total += ex.realized_pnl
            realized_count += 1

    match_rate = round(100 * realized_count / attributable_count) if attributable_count else 0
    return {
        "realized_pnl": format(total, "f"),
        "attributable_trades": attributable_count,
        "realized_trades": realized_count,
        "match_rate_percent": match_rate,
    }


def list_users(session: Session) -> list[dict[str, Any]]:
    assign_counts: dict[uuid.UUID, int] = {
        user_ref: count
        for user_ref, count in session.execute(
            select(StrategyAssignment.user_id, func.count()).group_by(StrategyAssignment.user_id)
        ).all()
    }
    users = session.scalars(select(User).order_by(User.created_at)).all()
    extra_roles = admin_accounts.extra_roles_by_user(session, [u.id for u in users])
    return [
        {
            "id": str(u.id),
            "email": u.email,
            "display_name": u.display_name,
            "role": u.role,
            "extra_roles": extra_roles.get(u.id, []),
            "is_active": u.is_active,
            # False while an admin-invited account hasn't completed its first
            # password setup yet (see app/services/admin_accounts.py) - the
            # Admin Team UI shows this as "Invited" rather than "Active".
            "has_password": u.password_hash is not None,
            "assignment_count": int(assign_counts.get(u.id, 0)),
        }
        for u in users
    ]


def ops_summary(session: Session) -> dict[str, Any]:
    """Admin-facing pipeline health (PRD 3.1, 11, 12): duplicate-signal,
    disconnected/stuck-execution, and broker-rejection visibility.

    Duplicate-signal rejection and stuck-in-UNKNOWN detection already exist
    at the data layer (signal_id uniqueness, ExecutionState.UNKNOWN); this is
    what surfaces them for an admin instead of only being visible in logs.
    """
    execution_state_counts = dict(
        session.execute(select(Execution.state, func.count()).group_by(Execution.state)).all()
    )
    total_signals = session.scalar(select(func.count()).select_from(Signal)) or 0
    total_executions = session.scalar(select(func.count()).select_from(Execution)) or 0
    revoked_assignments = (
        session.scalar(
            select(func.count())
            .select_from(StrategyAssignment)
            .where(StrategyAssignment.payment_status == "REVOKED")
        )
        or 0
    )
    duplicate_signal_count = (
        session.scalar(select(func.coalesce(func.sum(Signal.duplicate_attempts), 0))) or 0
    )
    mt5_disconnected_count = (
        session.scalar(
            select(func.count())
            .select_from(Mt5Connection)
            .where(
                Mt5Connection.status.in_(
                    [Mt5ConnectionStatus.DISCONNECTED.value, Mt5ConnectionStatus.ERROR.value]
                )
            )
        )
        or 0
    )

    return {
        "total_signals": total_signals,
        "total_executions": total_executions,
        "execution_state_counts": execution_state_counts,
        "stuck_unknown_count": execution_state_counts.get(ExecutionState.UNKNOWN.value, 0),
        "revoked_assignments": revoked_assignments,
        "duplicate_signal_count": int(duplicate_signal_count),
        "mt5_disconnected_count": mt5_disconnected_count,
        "broker_rejected_count": execution_state_counts.get(ExecutionState.REJECTED.value, 0),
    }


def list_assignments(session: Session) -> list[dict[str, Any]]:
    stmt = (
        select(StrategyAssignment, User, Strategy)
        .join(User, StrategyAssignment.user_id == User.id)
        .join(Strategy, StrategyAssignment.strategy_id == Strategy.id)
        .order_by(User.display_name)
    )
    return [
        {
            "id": str(a.id),
            "user_display_name": u.display_name,
            "strategy_key": s.strategy_key,
            "strategy_version": s.strategy_version,
            "master_lot": format(a.master_lot, "f"),
            "multiplier": format(a.multiplier, "f"),
            "multiplier_min": format(a.multiplier_min, "f"),
            "multiplier_max": format(a.multiplier_max, "f"),
            "status": a.status,
        }
        for a, u, s in session.execute(stmt).all()
    ]
