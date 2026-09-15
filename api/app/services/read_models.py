"""Read models for the dashboard APIs. Stored data only - no live computation."""

from __future__ import annotations

import uuid
from typing import Any

from protrix_contracts.db.models import (
    Execution,
    OrderIntent,
    Signal,
    Strategy,
    StrategyAssignment,
    User,
    UserRole,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session


def list_signals(
    session: Session, *, viewer_subject: str, viewer_role: UserRole, limit: int = 100
) -> list[dict[str, Any]]:
    intent_count_stmt = select(OrderIntent.signal_id, func.count()).group_by(OrderIntent.signal_id)
    signal_stmt = select(Signal).order_by(Signal.accepted_at.desc()).limit(limit)
    if viewer_role is UserRole.USER:
        intent_count_stmt = intent_count_stmt.where(OrderIntent.user_id == viewer_subject)
        # A user only sees signals that were actually fanned out to one of
        # their assignments. Signals are global ingress records, not public
        # user activity.
        signal_stmt = (
            select(Signal)
            .join(OrderIntent, OrderIntent.signal_id == Signal.id)
            .where(OrderIntent.user_id == viewer_subject)
            .distinct()
            .order_by(Signal.accepted_at.desc())
            .limit(limit)
        )
    intent_counts: dict[uuid.UUID, int] = {
        sig_id: count for sig_id, count in session.execute(intent_count_stmt).all()
    }
    rows = session.scalars(signal_stmt).all()
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
                "command_target": intent.command_target,
                "computed_lot": format(intent.computed_lot, "f"),
                "adapter": ex.adapter,
                "state": ex.state,
                "ticket_id": ex.ticket_id,
                "deal_id": ex.deal_id,
                "last_error": ex.last_error,
                "reconcile_count": ex.reconcile_count,
                "latency_dispatch_ms": ex.latency_dispatch_ms,
                "latency_ack_ms": ex.latency_ack_ms,
                "latency_fill_ms": ex.latency_fill_ms,
                "updated_at": ex.updated_at.isoformat(),
            }
        )
    return out


def list_users(session: Session) -> list[dict[str, Any]]:
    assign_counts: dict[uuid.UUID, int] = {
        user_ref: count
        for user_ref, count in session.execute(
            select(StrategyAssignment.user_id, func.count()).group_by(StrategyAssignment.user_id)
        ).all()
    }
    users = session.scalars(select(User).order_by(User.created_at)).all()
    return [
        {
            "id": str(u.id),
            "email": u.email,
            "display_name": u.display_name,
            "role": u.role,
            "is_active": u.is_active,
            "assignment_count": int(assign_counts.get(u.id, 0)),
        }
        for u in users
    ]


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
