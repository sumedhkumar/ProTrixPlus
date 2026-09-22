"""Execution lifecycle: happy path to FILLED, and timeout -> UNKNOWN ->
RECONCILED -> FILLED with no duplicate order."""

from __future__ import annotations

from decimal import Decimal

import pytest
from protrix_contracts.db.models import (
    AuditEvent,
    Execution,
    MockBrokerDeal,
    OrderIntent,
    Signal,
)
from protrix_contracts.lifecycle import ExecutionState
from sqlalchemy import func, select

from app.adapters.mock import MockExecutionAdapter
from app.execution import drive_new_execution
from tests.conftest import make_signal

pytestmark = pytest.mark.dbtest


def _make_intent(session, ids: dict, user: str) -> OrderIntent:
    sig = session.scalar(select(Signal))
    intent = OrderIntent(
        user_id=ids[user],
        strategy_id=ids["strategy"],
        signal_id=sig.id,
        command_target="ENTRY",
        action="BUY",
        symbol="EURUSD",
        computed_lot=Decimal("1.00"),
        master_lot=Decimal("1.00"),
        multiplier=Decimal("1.0000"),
        eligibility_status="ACTIVE",
        status="CREATED",
    )
    session.add(intent)
    session.flush()
    return intent


def _make_intent_for_signal(
    session, ids: dict, user: str, *, signal_id, command_target: str, action: str
) -> OrderIntent:
    intent = OrderIntent(
        user_id=ids[user],
        strategy_id=ids["strategy"],
        signal_id=signal_id,
        command_target=command_target,
        action=action,
        symbol="EURUSD",
        computed_lot=Decimal("1.00"),
        master_lot=Decimal("1.00"),
        multiplier=Decimal("1.0000"),
        eligibility_status="ACTIVE",
        status="CREATED",
    )
    session.add(intent)
    session.flush()
    return intent


@pytest.fixture
def ids(sf, seeded):
    make_signal(sf)
    return seeded


def test_happy_path_to_filled(sf, redis_client, ids) -> None:
    adapter = MockExecutionAdapter(sf, redis_client)
    with sf() as session:
        intent = _make_intent(session, ids, "alice")
        session.commit()
        execution = drive_new_execution(session, intent, adapter)
        session.commit()
        exec_id = execution.id

    with sf() as session:
        execution = session.get(Execution, exec_id)
        assert execution.state == ExecutionState.FILLED.value
        assert execution.ticket_id and execution.deal_id
        assert execution.latency_dispatch_ms is not None
        assert execution.latency_fill_ms is not None
        transitions = session.scalars(
            select(AuditEvent).where(AuditEvent.entity_id == str(exec_id))
        ).all()
        assert len(transitions) == 5  # RECEIVED -> INTENT_CREATED -> QUEUED -> DISPATCHED
        #                                        -> ACKNOWLEDGED -> FILLED  (5 edges)


def test_timeout_goes_unknown_then_reconciles_filled(sf, redis_client, ids) -> None:
    adapter = MockExecutionAdapter(sf, redis_client)
    adapter.arm_timeout_once()

    with sf() as session:
        intent = _make_intent(session, ids, "bob")
        session.commit()
        execution = drive_new_execution(session, intent, adapter)
        session.commit()
        exec_id, intent_id = execution.id, intent.id

    with sf() as session:
        execution = session.get(Execution, exec_id)
        assert execution.state == ExecutionState.FILLED.value
        assert execution.reconcile_count == 1
        assert execution.last_error is None or "timeout" in execution.last_error.lower()

        deals = session.scalar(
            select(func.count())
            .select_from(MockBrokerDeal)
            .where(MockBrokerDeal.client_order_id == str(intent_id))
        )
        assert deals == 1  # no duplicate order

        # transitions include ...DISPATCHED -> UNKNOWN -> RECONCILED -> FILLED
        states = [
            e.data["to"]
            for e in session.scalars(
                select(AuditEvent)
                .where(AuditEvent.entity_id == str(exec_id))
                .order_by(AuditEvent.id)
            ).all()
        ]
        assert "UNKNOWN" in states
        assert "RECONCILED" in states
        assert states[-1] == "FILLED"
        assert "DISPATCHED" not in states[states.index("UNKNOWN") + 1 :]  # never re-sent


def test_close_signal_fills_by_closing_the_matching_entry(sf, redis_client, seeded) -> None:
    """A CLOSE-family signal with a matching position_ref resolves against the
    open ENTRY (not a fresh position) and reaches FILLED, with the entry's own
    execution row carrying the exit_price/realized_pnl."""
    adapter = MockExecutionAdapter(sf, redis_client)
    entry_sig_id = make_signal(sf, signal_id="sig-entry-close-1", action="BUY", position_ref="pos-x")
    close_sig_id = make_signal(sf, signal_id="sig-entry-close-2", action="CLOSE", position_ref="pos-x")

    with sf() as session:
        entry_intent = _make_intent_for_signal(
            session, seeded, "alice", signal_id=entry_sig_id, command_target="ENTRY", action="BUY"
        )
        session.commit()
        entry_execution = drive_new_execution(session, entry_intent, adapter)
        session.commit()
        entry_exec_id = entry_execution.id
        assert entry_execution.state == ExecutionState.FILLED.value
        assert entry_execution.entry_price is not None

    with sf() as session:
        close_intent = _make_intent_for_signal(
            session, seeded, "alice", signal_id=close_sig_id, command_target="CLOSE", action="CLOSE"
        )
        session.commit()
        close_execution = drive_new_execution(session, close_intent, adapter)
        session.commit()
        assert close_execution.state == ExecutionState.FILLED.value
        assert close_execution.ticket_id == session.get(Execution, entry_exec_id).ticket_id

    with sf() as session:
        entry_execution = session.get(Execution, entry_exec_id)
        assert entry_execution.exit_price is not None
        assert entry_execution.realized_pnl is not None


def test_close_signal_with_no_matching_position_is_rejected_cleanly(sf, redis_client, seeded) -> None:
    """A CLOSE signal whose position_ref was never opened must reach REJECTED,
    not raise, and not leave the state machine in an inconsistent place."""
    adapter = MockExecutionAdapter(sf, redis_client)
    close_sig_id = make_signal(sf, signal_id="sig-orphan-close-1", action="CLOSE", position_ref="never-opened")

    with sf() as session:
        close_intent = _make_intent_for_signal(
            session, seeded, "alice", signal_id=close_sig_id, command_target="CLOSE", action="CLOSE"
        )
        session.commit()
        close_execution = drive_new_execution(session, close_intent, adapter)
        session.commit()
        exec_id = close_execution.id

    with sf() as session:
        close_execution = session.get(Execution, exec_id)
        assert close_execution.state == ExecutionState.REJECTED.value
