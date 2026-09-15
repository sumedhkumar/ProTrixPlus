"""Safe background reconciliation for uncertain entry executions."""

from __future__ import annotations

import logging

from protrix_contracts.db.models import Execution, OrderIntent, User
from protrix_contracts.lifecycle import ExecutionState
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.base import ExecutionAdapter
from app.execution import reconcile_unknown

log = logging.getLogger("worker.reconciliation")


def reconcile_pending_entries(
    session_factory: sessionmaker[Session],
    adapter: ExecutionAdapter,
    *,
    active_user_email: str | None = None,
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
