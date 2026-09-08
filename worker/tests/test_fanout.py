"""Fan-out: one intent + one execution per eligible user; replays are no-ops."""

from __future__ import annotations

import pytest
from protrix_contracts.db.models import Execution, OrderIntent
from protrix_contracts.lifecycle import ExecutionState
from sqlalchemy import func, select

from app.adapters.mock import MockExecutionAdapter
from app.fanout import process_signal
from tests.conftest import make_signal

pytestmark = pytest.mark.dbtest


def test_fan_out_creates_one_intent_and_execution_per_user(sf, redis_client, seeded) -> None:
    signal_row_id = make_signal(sf)
    adapter = MockExecutionAdapter(sf, redis_client)

    with sf() as session:
        process_signal(session, signal_row_id, adapter)

    with sf() as session:
        assert session.scalar(select(func.count()).select_from(OrderIntent)) == 2
        assert session.scalar(select(func.count()).select_from(Execution)) == 2
        assert set(session.scalars(select(Execution.state)).all()) == {ExecutionState.FILLED.value}


def test_replaying_the_same_signal_creates_no_duplicates(sf, redis_client, seeded) -> None:
    signal_row_id = make_signal(sf)
    adapter = MockExecutionAdapter(sf, redis_client)

    for _ in range(3):
        with sf() as session:
            process_signal(session, signal_row_id, adapter)

    with sf() as session:
        assert session.scalar(select(func.count()).select_from(OrderIntent)) == 2
        assert session.scalar(select(func.count()).select_from(Execution)) == 2


def test_duplicate_intent_is_blocked_by_db_constraint(sf, seeded) -> None:
    from decimal import Decimal

    from sqlalchemy.exc import IntegrityError

    signal_row_id = make_signal(sf)

    def _row(session):
        return OrderIntent(
            user_id=seeded["alice"],
            strategy_id=seeded["strategy"],
            signal_id=signal_row_id,
            command_target="ENTRY",
            action="BUY",
            symbol="EURUSD",
            computed_lot=Decimal("1.00"),
            master_lot=Decimal("1.00"),
            multiplier=Decimal("1.0000"),
            eligibility_status="ACTIVE",
            status="CREATED",
        )

    with sf() as session:
        session.add(_row(session))
        session.commit()

    with pytest.raises(IntegrityError), sf() as session:
        session.add(_row(session))
        session.commit()
