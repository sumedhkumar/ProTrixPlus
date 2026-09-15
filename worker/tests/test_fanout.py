"""Fan-out: one intent + one execution per eligible user; replays are no-ops."""

from __future__ import annotations

import pytest
from protrix_contracts.db.models import Execution, ManagedPosition, OrderIntent, TradingControl
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
            execution_key="entry",
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


def test_mapped_close_bypasses_entry_blocks_and_closes_only_managed_positions(
    sf, redis_client, seeded
) -> None:
    """An exit remains available after a user is suspended; entries do not."""
    adapter = MockExecutionAdapter(sf, redis_client)
    entry_row_id = make_signal(sf, signal_id="entry-managed")
    with sf() as session:
        process_signal(session, entry_row_id, adapter)

    with sf() as session:
        alice_control = session.scalar(
            select(TradingControl).where(TradingControl.user_id == seeded["alice"])
        )
        assert alice_control is not None
        alice_control.kill_switch = True
        session.commit()

    close_row_id = make_signal(
        sf,
        signal_id="close-managed",
        action="CLOSE",
        position_ref="entry-managed",
    )
    with sf() as session:
        touched = process_signal(session, close_row_id, adapter)
        assert len(touched) == 2

    with sf() as session:
        positions = session.scalars(select(ManagedPosition)).all()
        assert len(positions) == 2
        assert {position.status for position in positions} == {"CLOSED"}
        assert {position.remaining_volume for position in positions} == {0}


def test_directional_signal_reverses_managed_position_without_explicit_close_alert(
    sf, redis_client, seeded
) -> None:
    adapter = MockExecutionAdapter(sf, redis_client)
    buy_row_id = make_signal(sf, signal_id="buy-only-alert", action="BUY")
    with sf() as session:
        process_signal(
            session,
            buy_row_id,
            adapter,
            active_user_email="alice@example.test",
        )

    sell_row_id = make_signal(sf, signal_id="sell-only-alert", action="SELL")
    with sf() as session:
        touched = process_signal(
            session,
            sell_row_id,
            adapter,
            active_user_email="alice@example.test",
        )
        assert len(touched) == 2  # mapped CLOSE, then SELL entry

    with sf() as session:
        positions = session.scalars(
            select(ManagedPosition).order_by(ManagedPosition.created_at)
        ).all()
        assert len(positions) == 2
        assert positions[0].side == "BUY"
        assert positions[0].status == "CLOSED"
        assert positions[1].side == "SELL"
        assert positions[1].status == "OPEN"

        intents = session.scalars(select(OrderIntent).order_by(OrderIntent.created_at)).all()
        assert [(intent.action, intent.execution_key) for intent in intents] == [
            ("BUY", "entry"),
            ("CLOSE", "buy-only-alert"),
            ("SELL", "entry"),
        ]
