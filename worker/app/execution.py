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

from protrix_contracts.db.models import AuditEvent, Execution, Mt5Connection, OrderIntent
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


def _resolve_account_ref(session: Session, intent: OrderIntent, adapter_name: str) -> str | None:
    """The transport account reference passed to ``adapter.place``/``sync_positions``.

    ``mock`` and the native ``mt5`` adapter (single terminal, single account)
    don't need per-user routing - a synthetic label is enough. ``metaapi`` is
    genuinely multi-tenant: each client's signal must land on *their own*
    MetaApi account, never a shared one. Returns ``None`` when that adapter
    needs a real connection this user doesn't have yet, so the caller can
    reject cleanly instead of dispatching into a broker call that can't route
    anywhere.
    """
    if adapter_name != "metaapi":
        return f"acct-{intent.user_id}"

    conn = session.scalar(select(Mt5Connection).where(Mt5Connection.user_id == intent.user_id))
    if conn is None or not conn.metaapi_account_id or not conn.metaapi_region:
        return None
    return f"{conn.metaapi_region}:{conn.metaapi_account_id}"


def _dto(intent: OrderIntent, client_order_id: str, account_ref: str) -> OrderIntentDTO:
    signal = intent.signal
    return OrderIntentDTO(
        client_order_id=client_order_id,
        account_ref=account_ref,
        symbol=intent.symbol,
        side="SELL" if intent.action.upper() == "SELL" else "BUY",
        volume=intent.computed_lot,
        action=intent.action,
        command_target=intent.command_target,
        stop_loss=signal.stop_loss if signal else None,
        take_profit=signal.take_profit if signal else None,
        position_ref=signal.position_ref if signal else None,
        close_fraction=signal.close_fraction if signal else None,
        user_id=str(intent.user_id),
        strategy_key=signal.strategy_key if signal else None,
        strategy_version=signal.strategy_version if signal else None,
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

    account_ref = _resolve_account_ref(session, intent, adapter.name)
    if account_ref is None:
        execution.last_error = f"no {adapter.name} account connected for this user"
        _advance(session, execution, ExecutionState.REJECTED)
        log.warning(
            "execution %s REJECTED: no %s account connected for user=%s",
            execution.id,
            adapter.name,
            intent.user_id,
        )
        return execution

    _advance(session, execution, ExecutionState.INTENT_CREATED, ts_attr="intent_created_at")
    _advance(session, execution, ExecutionState.QUEUED, ts_attr="queued_at")
    _advance(session, execution, ExecutionState.DISPATCHED, ts_attr="dispatched_at")

    try:
        result = adapter.place(_dto(intent, execution.client_order_id, account_ref))
    except ExecutionTimeout as exc:
        execution.last_error = str(exc)
        _advance(session, execution, ExecutionState.UNKNOWN)
        log.warning("execution %s UNKNOWN after dispatch: %s", execution.id, exc)
        reconcile_unknown(session, execution, adapter)
        return execution

    execution.ticket_id = result.ticket_id
    execution.deal_id = result.deal_id
    if result.entry_price is not None:
        execution.entry_price = result.entry_price
    if result.status == "REJECTED":
        # PlaceResult.raw carries the adapter's real rejection reason (broker
        # error message, retcode, etc.) - surface it instead of leaving
        # last_error blank, or a REJECTED execution is undebuggable.
        if result.raw:
            execution.last_error = "; ".join(f"{k}={v}" for k, v in result.raw.items())
        _advance(session, execution, ExecutionState.REJECTED)
        log.info("execution %s REJECTED: %s", execution.id, execution.last_error)
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
    account_ref = _resolve_account_ref(session, intent, adapter.name) if intent else None
    if account_ref is None:
        # Only reachable if the account was resolvable at dispatch time (that
        # gate runs before DISPATCHED) but stopped being so before reconcile -
        # e.g. an admin detached the connection in between. Nothing to
        # reconcile against; leave it UNKNOWN (unchanged) rather than guess.
        execution.last_error = f"reconcile: no {adapter.name} account to reconcile against"
        log.error("execution %s: account_ref no longer resolvable for reconcile", execution.id)
        return execution
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
