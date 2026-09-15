"""Execution lifecycle: happy path to FILLED, and timeout -> UNKNOWN ->
RECONCILED -> FILLED with no duplicate order."""

from __future__ import annotations

from decimal import Decimal

import pytest
from protrix_contracts.db.models import (
    AuditEvent,
    Execution,
    ManagedPosition,
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
        execution_key="entry",
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
        managed = session.scalar(
            select(ManagedPosition).where(ManagedPosition.entry_execution_id == exec_id)
        )
        assert managed is not None
        assert managed.status == "OPEN"
        assert managed.remaining_volume == Decimal("1.00")
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
