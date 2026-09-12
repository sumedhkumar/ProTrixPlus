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

from protrix_contracts.db.models import AuditEvent, Execution, OrderIntent
from protrix_contracts.lifecycle import ExecutionState, assert_transition
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


def _account_ref(intent: OrderIntent) -> str:
    return f"acct-{intent.user_id}"


def _dto(intent: OrderIntent, client_order_id: str) -> OrderIntentDTO:
    signal = intent.signal
    return OrderIntentDTO(
        client_order_id=client_order_id,
        account_ref=_account_ref(intent),
        symbol=intent.symbol,
        side="SELL" if intent.action.upper() == "SELL" else "BUY",
        volume=intent.computed_lot,
        action=intent.action,
        command_target=intent.command_target,
        stop_loss=signal.stop_loss if signal else None,
        take_profit=signal.take_profit if signal else None,
        position_ref=signal.position_ref if signal else None,
        close_fraction=signal.close_fraction if signal else None,
    )


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
        result = adapter.place(_dto(intent, execution.client_order_id))
    except ExecutionTimeout as exc:
        execution.last_error = str(exc)
        _advance(session, execution, ExecutionState.UNKNOWN)
        log.warning("execution %s UNKNOWN after dispatch: %s", execution.id, exc)
        reconcile_unknown(session, execution, adapter)
        return execution

    execution.ticket_id = result.ticket_id
    execution.deal_id = result.deal_id
    if result.status == "REJECTED":
        _advance(session, execution, ExecutionState.REJECTED)
        return execution

    _advance(session, execution, ExecutionState.ACKNOWLEDGED, ts_attr="acknowledged_at")
    _advance(session, execution, ExecutionState.FILLED, ts_attr="filled_at")
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
    account_ref = _account_ref(intent) if intent else ""
    positions = adapter.sync_positions(account_ref)
    match = next((p for p in positions if p.client_order_id == execution.client_order_id), None)

    execution.reconcile_count += 1
    _advance(session, execution, ExecutionState.RECONCILED, ts_attr="reconciled_at")

    if match is not None:
        execution.ticket_id = match.ticket_id
        execution.deal_id = match.deal_id
        _advance(session, execution, ExecutionState.FILLED, ts_attr="filled_at")
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
