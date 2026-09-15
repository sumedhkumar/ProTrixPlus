"""Native-account heartbeats and safe UNKNOWN reconciliation."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from protrix_contracts.db.models import Execution, OrderIntent, Signal, TradingAccount
from protrix_contracts.lifecycle import ExecutionState
from sqlalchemy import func, select

from app.adapters.mock import MockExecutionAdapter
from app.heartbeat import record_heartbeat
from app.reconciliation import reconcile_pending_entries
from tests.conftest import make_signal

pytestmark = pytest.mark.dbtest


def _unknown_execution(session, ids: dict, *, command_target: str = "ENTRY") -> Execution:
    signal = session.scalar(select(Signal))
    assert signal is not None
    intent = OrderIntent(
        user_id=ids["alice"],
        strategy_id=ids["strategy"],
        signal_id=signal.id,
        command_target=command_target,
        execution_key="entry" if command_target == "ENTRY" else signal.signal_id,
        action="BUY" if command_target == "ENTRY" else "CLOSE",
        symbol="EURUSD",
        computed_lot=Decimal("1.00"),
        master_lot=Decimal("1.00"),
        multiplier=Decimal("1.0000"),
        eligibility_status="ACTIVE",
        status="CREATED",
    )
    session.add(intent)
    session.flush()
    execution = Execution(
        order_intent_id=intent.id,
        client_order_id=str(intent.id),
        adapter="mock",
        state=ExecutionState.UNKNOWN.value,
        received_at=datetime.now(UTC),
    )
    session.add(execution)
    session.flush()
    return execution


def test_native_worker_heartbeat_is_scoped_to_its_configured_user(sf, seeded) -> None:
    cfg = SimpleNamespace(
        execution_adapter="mt5",
        mt5_user_email="alice@example.test",
        consumer_name="alice-native",
    )

    assert record_heartbeat(sf, cfg) is True

    with sf() as session:
        account = session.scalar(
            select(TradingAccount).where(TradingAccount.user_id == seeded["alice"])
        )
        assert account is not None
        assert account.worker_adapter == "mt5"
        assert account.worker_name == "alice-native"
        assert account.worker_heartbeat_at is not None


def test_reconciliation_rejects_missing_unknown_entry_without_resend(
    sf, redis_client, seeded
) -> None:
    make_signal(sf)
    with sf() as session:
        execution = _unknown_execution(session, seeded)
        execution_id = execution.id
        session.commit()

    adapter = MockExecutionAdapter(sf, redis_client)
    assert reconcile_pending_entries(sf, adapter, active_user_email="alice@example.test") == 1

    with sf() as session:
        execution = session.get(Execution, execution_id)
        assert execution is not None
        assert execution.state == ExecutionState.REJECTED.value
        assert execution.reconcile_count == 1
        assert session.scalar(select(func.count()).select_from(Execution)) == 1


def test_reconciliation_leaves_unknown_management_for_operator_review(
    sf, redis_client, seeded
) -> None:
    make_signal(sf)
    with sf() as session:
        execution = _unknown_execution(session, seeded, command_target="CLOSE")
        execution_id = execution.id
        session.commit()

    adapter = MockExecutionAdapter(sf, redis_client)
    assert reconcile_pending_entries(sf, adapter, active_user_email="alice@example.test") == 0

    with sf() as session:
        execution = session.get(Execution, execution_id)
        assert execution is not None
        assert execution.state == ExecutionState.UNKNOWN.value
        assert execution.reconcile_count == 0
