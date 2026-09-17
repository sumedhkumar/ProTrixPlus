"""Execution lifecycle driver.

Creates the execution row and walks it through the state machine, persisting and
audit-logging every transition. Two entry points:

* :func:`drive_new_execution` - the happy path
  RECEIVED -> INTENT_CREATED -> QUEUED -> DISPATCHED -> ACKNOWLEDGED -> FILLED,
  or the timeout branch DISPATCHED -> UNKNOWN -> (reconcile).
* :func:`reconcile_unknown` - resolves an UNKNOWN execution from broker state.
  UNKNOWN -> RECONCILED -> FILLED / REJECTED. Never re-sends the order.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal

from protrix_contracts.db.models import (
    AuditEvent,
    EnrollmentAccount,
    Execution,
    ManagedPosition,
    ManagedPositionStatus,
    OrderIntent,
)
from protrix_contracts.lifecycle import ExecutionState, assert_transition
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.base import ExecutionAdapter, ExecutionTimeout, OrderIntentDTO

log = logging.getLogger("worker.execution")


def _now() -> datetime:
    return datetime.now(UTC)


def _ms(a: datetime | None, b: datetime | None) -> int | None:
    if a is None or b is None:
        return None
    return int((b - a).total_seconds() * 1000)


def _advance(
    session: Session,
    execution: Execution,
    new_state: ExecutionState,
    *,
    ts_attr: str | None = None,
) -> None:
    assert_transition(execution.state, new_state)
    prev = execution.state
    execution.state = new_state.value
    if ts_attr is not None:
        setattr(execution, ts_attr, _now())
    execution.latency_queue_ms = _ms(execution.intent_created_at, execution.queued_at)
    execution.latency_dispatch_ms = _ms(execution.queued_at, execution.dispatched_at)
    execution.latency_ack_ms = _ms(execution.dispatched_at, execution.acknowledged_at)
    execution.latency_fill_ms = _ms(execution.acknowledged_at, execution.filled_at)
    session.add(
        AuditEvent(
            event_type="execution.transition",
            entity_type="execution",
            entity_id=str(execution.id),
            actor="worker",
            data={"from": prev, "to": new_state.value},
        )
    )
    session.flush()


def _account_ref(session: Session, intent: OrderIntent) -> str:
    if intent.enrollment_id is not None:
        account = session.scalar(
            select(EnrollmentAccount).where(EnrollmentAccount.enrollment_id == intent.enrollment_id)
        )
        if account is not None:
            return account.external_account_ref or f"enrollment-{intent.enrollment_id}"
    return f"acct-{intent.user_id}"


def _dto(session: Session, intent: OrderIntent, client_order_id: str) -> OrderIntentDTO:
    signal = intent.signal
    managed_position = None
    position_ref = signal.position_ref if signal else None
    if intent.command_target != "ENTRY":
        position_ref = position_ref or intent.execution_key
        managed_position = session.scalar(
            select(ManagedPosition).where(
                ManagedPosition.user_id == intent.user_id,
                ManagedPosition.strategy_id == intent.strategy_id,
                ManagedPosition.source_position_ref == position_ref,
                ManagedPosition.status == ManagedPositionStatus.OPEN.value,
            )
        )
    return OrderIntentDTO(
        client_order_id=client_order_id,
        account_ref=_account_ref(session, intent),
        symbol=intent.symbol,
        side="SELL" if intent.action.upper() == "SELL" else "BUY",
        volume=intent.computed_lot,
        action=intent.action,
        command_target=intent.command_target,
        stop_loss=signal.stop_loss if signal else None,
        take_profit=signal.take_profit if signal else None,
        position_ref=position_ref,
        broker_position_ref=managed_position.broker_position_ref if managed_position else None,
        close_fraction=signal.close_fraction if signal else None,
    )


def _record_managed_entry(session: Session, execution: Execution) -> None:
    """Persist the user-owned broker-position mapping after a filled entry.

    Management commands must use this mapping instead of an arbitrary ticket
    supplied by an alert.  It is deliberately written only after the execution
    is filled and is idempotent for reconciliation/restart paths.
    """
    intent = execution.order_intent
    if intent.command_target != "ENTRY" or intent.action.upper() not in {"BUY", "SELL"}:
        return
    if session.scalar(
        select(ManagedPosition.id).where(ManagedPosition.entry_execution_id == execution.id)
    ):
        return

    signal = intent.signal
    source_position_ref = signal.position_ref or signal.signal_id
    broker_position_ref = execution.ticket_id or execution.deal_id or execution.client_order_id
    position = ManagedPosition(
        user_id=intent.user_id,
        strategy_id=intent.strategy_id,
        entry_execution_id=execution.id,
        source_position_ref=source_position_ref,
        broker_position_ref=broker_position_ref,
        symbol=intent.symbol,
        side=intent.action.upper(),
        initial_volume=intent.computed_lot,
        remaining_volume=intent.computed_lot,
        status=ManagedPositionStatus.OPEN.value,
    )
    session.add(position)
    session.add(
        AuditEvent(
            event_type="managed_position.opened",
            entity_type="managed_position",
            entity_id=str(position.id),
            actor="worker",
            data={
                "execution_id": str(execution.id),
                "source_position_ref": source_position_ref,
                "broker_position_ref": broker_position_ref,
            },
        )
    )
    session.flush()


def _record_management_outcome(session: Session, execution: Execution) -> None:
    """Update a managed position only after the broker acknowledged success."""
    intent = execution.order_intent
    if intent.command_target == "ENTRY":
        return
    signal = intent.signal
    if signal is None:
        return
    position_ref = signal.position_ref or intent.execution_key
    position = session.scalar(
        select(ManagedPosition).where(
            ManagedPosition.user_id == intent.user_id,
            ManagedPosition.strategy_id == intent.strategy_id,
            ManagedPosition.source_position_ref == position_ref,
            ManagedPosition.status == ManagedPositionStatus.OPEN.value,
        )
    )
    if position is None:
        return
    action = intent.action.upper()
    if action in {"CLOSE", "EMERGENCY_CLOSE"}:
        position.remaining_volume = Decimal("0")
        position.status = ManagedPositionStatus.CLOSED.value
    elif action == "PARTIAL_CLOSE" and signal.close_fraction is not None:
        remaining = Decimal(position.remaining_volume) * (Decimal("1") - signal.close_fraction)
        position.remaining_volume = max(Decimal("0"), remaining)
        if position.remaining_volume == 0:
            position.status = ManagedPositionStatus.CLOSED.value
    else:
        return
    session.add(
        AuditEvent(
            event_type="managed_position.updated",
            entity_type="managed_position",
            entity_id=str(position.id),
            actor="worker",
            data={
                "execution_id": str(execution.id),
                "action": action,
                "status": position.status,
                "remaining_volume": format(position.remaining_volume, "f"),
            },
        )
    )
    session.flush()


def drive_new_execution(
    session: Session, intent: OrderIntent, adapter: ExecutionAdapter
) -> Execution:
    now = _now()
    execution = Execution(
        order_intent_id=intent.id,
        client_order_id=str(intent.id),
        adapter=adapter.name,
        state=ExecutionState.RECEIVED.value,
        received_at=now,
    )
    session.add(execution)
    session.flush()

    _advance(session, execution, ExecutionState.INTENT_CREATED, ts_attr="intent_created_at")
    _advance(session, execution, ExecutionState.QUEUED, ts_attr="queued_at")
    _advance(session, execution, ExecutionState.DISPATCHED, ts_attr="dispatched_at")

    try:
        result = adapter.place(_dto(session, intent, execution.client_order_id))
    except ExecutionTimeout as exc:
        execution.last_error = str(exc)
        _advance(session, execution, ExecutionState.UNKNOWN)
        log.warning("execution %s UNKNOWN after dispatch: %s", execution.id, exc)
        if intent.command_target == "ENTRY":
            reconcile_unknown(session, execution, adapter)
        else:
            log.error(
                "management execution %s is UNKNOWN; it will not be resent; "
                "broker reconciliation is required",
                execution.id,
            )
        return execution

    execution.ticket_id = result.ticket_id
    execution.deal_id = result.deal_id
    if result.status == "REJECTED":
        execution.last_error = result.raw.get("reason") or result.raw.get("comment") or str(
            result.raw
        )
        _advance(session, execution, ExecutionState.REJECTED)
        log.error("execution %s REJECTED: %s", execution.id, execution.last_error)
        return execution

    _advance(session, execution, ExecutionState.ACKNOWLEDGED, ts_attr="acknowledged_at")
    _advance(session, execution, ExecutionState.FILLED, ts_attr="filled_at")
    _record_managed_entry(session, execution)
    _record_management_outcome(session, execution)
    log.info(
        "execution %s FILLED ticket=%s deal=%s lot=%s",
        execution.id,
        execution.ticket_id,
        execution.deal_id,
        intent.computed_lot,
    )
    return execution


def reconcile_unknown(
    session: Session, execution: Execution, adapter: ExecutionAdapter
) -> Execution:
    """Resolve an UNKNOWN execution by asking the broker what actually happened.
    No order is ever re-sent from here."""
    if execution.state != ExecutionState.UNKNOWN.value:
        raise ValueError(f"reconcile called on non-UNKNOWN execution {execution.id}")

    intent = session.get(OrderIntent, execution.order_intent_id)
    if intent is not None and intent.command_target != "ENTRY":
        # A position snapshot can prove an entry exists, but cannot safely
        # prove that a close/modify request with a lost response did *not*
        # reach the broker. Keep UNKNOWN and never re-send it.
        execution.reconcile_count += 1
        session.add(
            AuditEvent(
                event_type="execution.management_reconciliation_deferred",
                entity_type="execution",
                entity_id=str(execution.id),
                actor="worker",
                data={"command_target": intent.command_target},
            )
        )
        session.flush()
        return execution
    account_ref = _account_ref(session, intent) if intent else ""
    positions = adapter.sync_positions(account_ref)
    match = next((p for p in positions if p.client_order_id == execution.client_order_id), None)

    execution.reconcile_count += 1
    _advance(session, execution, ExecutionState.RECONCILED, ts_attr="reconciled_at")

    if match is not None:
        execution.ticket_id = match.ticket_id
        execution.deal_id = match.deal_id
        _advance(session, execution, ExecutionState.FILLED, ts_attr="filled_at")
        _record_managed_entry(session, execution)
        _record_management_outcome(session, execution)
        log.info(
            "execution %s reconciled -> FILLED (broker had ticket %s)",
            execution.id,
            match.ticket_id,
        )
    else:
        execution.last_error = "reconcile: no broker position; order never placed"
        _advance(session, execution, ExecutionState.REJECTED)
        log.info("execution %s reconciled -> REJECTED (broker never saw it)", execution.id)
    return execution
