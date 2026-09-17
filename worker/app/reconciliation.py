"""Safe background reconciliation for uncertain entry executions."""

from __future__ import annotations

import logging
import uuid

from protrix_contracts.db.models import (
    EnrollmentAccount,
    Execution,
    OrderIntent,
    TradingAccount,
    User,
)
from protrix_contracts.lifecycle import ExecutionState
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.base import ExecutionAdapter
from app.execution import reconcile_unknown

log = logging.getLogger("worker.reconciliation")


def reconcile_pending_entries(
    session_factory: sessionmaker[Session],
    adapter: ExecutionAdapter,
    *,
    active_user_email: str | None = None,
    active_enrollment_id: uuid.UUID | None = None,
    active_transport: str | None = None,
    limit: int = 100,
) -> int:
    """Ask the broker about UNKNOWN entry orders; never place a new order.

    Management requests intentionally remain UNKNOWN for operator review because
    a position snapshot cannot safely prove whether a lost close/modify request
    reached the broker.
    """
    with session_factory() as session:
        stmt = (
            select(Execution.id)
            .join(OrderIntent, Execution.order_intent_id == OrderIntent.id)
            .where(
                Execution.state == ExecutionState.UNKNOWN.value,
                OrderIntent.command_target == "ENTRY",
            )
            .order_by(Execution.updated_at)
            .limit(limit)
        )
        if active_user_email:
            stmt = stmt.join(User, OrderIntent.user_id == User.id).where(
                User.email == active_user_email
            )
        if active_enrollment_id is not None:
            stmt = stmt.where(OrderIntent.enrollment_id == active_enrollment_id)
        if active_transport is not None:
            stmt = (
                stmt.outerjoin(
                    EnrollmentAccount,
                    EnrollmentAccount.enrollment_id == OrderIntent.enrollment_id,
                )
                .outerjoin(TradingAccount, TradingAccount.user_id == OrderIntent.user_id)
                .where(
                    or_(
                        and_(
                            OrderIntent.enrollment_id.is_not(None),
                            EnrollmentAccount.transport == active_transport,
                        ),
                        and_(
                            OrderIntent.enrollment_id.is_(None),
                            TradingAccount.transport == active_transport,
                        ),
                    )
                )
            )
        execution_ids = list(session.scalars(stmt))

    reconciled = 0
    for execution_id in execution_ids:
        with session_factory() as session:
            execution = session.get(Execution, execution_id)
            if execution is None or execution.state != ExecutionState.UNKNOWN.value:
                continue
            try:
                reconcile_unknown(session, execution, adapter)
                session.commit()
                reconciled += 1
            except Exception:  # noqa: BLE001
                session.rollback()
                log.exception("reconciliation failed for execution %s", execution_id)
    if execution_ids:
        log.info("reconciliation checked=%d resolved=%d", len(execution_ids), reconciled)
    return reconciled
