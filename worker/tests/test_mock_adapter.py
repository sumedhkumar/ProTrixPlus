"""MockExecutionAdapter: deterministic ids, durable mock broker state, one-shot
timeout that still leaves a reconcilable position, and CLOSE/MODIFY resolution
against the correct previously-opened position."""

from __future__ import annotations

import uuid
from decimal import ROUND_HALF_EVEN, Decimal

import pytest
from protrix_contracts.db.models import Execution, MockBrokerDeal, OrderIntent
from sqlalchemy import func, select

from app.adapters.base import ExecutionTimeout, OrderIntentDTO
from app.adapters.mock import MockExecutionAdapter, _mock_price
from app.execution import drive_new_execution
from tests.conftest import STRATEGY_KEY, STRATEGY_VERSION, make_signal

pytestmark = pytest.mark.dbtest


def _order(coid: str = "coid-1") -> OrderIntentDTO:
    return OrderIntentDTO(
        client_order_id=coid,
        account_ref="acct-x",
        symbol="EURUSD",
        side="BUY",
        volume=Decimal("1.00"),
        action="BUY",
        command_target="ENTRY",
    )


def _seed_open_entry(
    sf, adapter: MockExecutionAdapter, ids: dict, user: str, *, signal_id: str, position_ref: str
) -> uuid.UUID:
    """Drive a real ENTRY through the full pipeline so an Execution row exists
    with a client_order_id the mock broker deal can be joined against - a
    bare adapter.place() call (as _order()'s DTO-only tests use) never
    creates that Execution row, so a later CLOSE would have nothing to join
    to. Returns the resulting Execution's id."""
    sig_id = make_signal(sf, signal_id=signal_id, action="BUY", position_ref=position_ref)
    with sf() as session:
        intent = OrderIntent(
            user_id=ids[user],
            strategy_id=ids["strategy"],
            signal_id=sig_id,
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
        session.commit()
        execution = drive_new_execution(session, intent, adapter)
        session.commit()
        return execution.id


def _close_order(
    coid: str, *, user_id: uuid.UUID, position_ref: str, action: str = "CLOSE"
) -> OrderIntentDTO:
    return OrderIntentDTO(
        client_order_id=coid,
        account_ref=f"acct-{user_id}",
        symbol="EURUSD",
        side="BUY",
        volume=Decimal("1.00"),
        action=action,
        command_target="CLOSE",
        position_ref=position_ref,
        user_id=str(user_id),
        strategy_key=STRATEGY_KEY,
        strategy_version=STRATEGY_VERSION,
    )


def _modify_order(coid: str, *, user_id: uuid.UUID, position_ref: str) -> OrderIntentDTO:
    return OrderIntentDTO(
        client_order_id=coid,
        account_ref=f"acct-{user_id}",
        symbol="EURUSD",
        side="BUY",
        volume=Decimal("1.00"),
        action="MODIFY_SLTP",
        command_target="MODIFY",
        position_ref=position_ref,
        user_id=str(user_id),
        strategy_key=STRATEGY_KEY,
        strategy_version=STRATEGY_VERSION,
    )


def test_place_is_deterministic_and_records_broker_state(sf, redis_client, clean_db) -> None:
    adapter = MockExecutionAdapter(sf, redis_client)
    r1 = adapter.place(_order("coid-1"))
    r2 = adapter.place(_order("coid-1"))
    assert (r1.ticket_id, r1.deal_id) == (r2.ticket_id, r2.deal_id)
    assert r1.status == "ACKNOWLEDGED"
    assert r1.entry_price is not None

    positions = adapter.sync_positions("acct-x")
    assert any(p.client_order_id == "coid-1" for p in positions)


def test_armed_timeout_raises_once_but_leaves_position(sf, redis_client, clean_db) -> None:
    adapter = MockExecutionAdapter(sf, redis_client)
    adapter.arm_timeout_once()

    with pytest.raises(ExecutionTimeout):
        adapter.place(_order("coid-timeout"))

    # The broker still has the position (lost response, not lost order).
    positions = adapter.sync_positions("acct-x")
    assert any(p.client_order_id == "coid-timeout" for p in positions)

    # Timeout is one-shot: a retry would now succeed (worker never does this).
    result = adapter.place(_order("coid-timeout"))
    assert result.status == "ACKNOWLEDGED"
    assert result.entry_price is not None


def test_close_matches_open_position_and_computes_pnl(sf, redis_client, seeded) -> None:
    adapter = MockExecutionAdapter(sf, redis_client)
    exec_id = _seed_open_entry(
        sf, adapter, seeded, "alice", signal_id="sig-close-1", position_ref="pos-1"
    )

    close_coid = "coid-close-1"
    result = adapter.place(_close_order(close_coid, user_id=seeded["alice"], position_ref="pos-1"))
    assert result.status == "ACKNOWLEDGED"

    with sf() as session:
        entry_execution = session.get(Execution, exec_id)
        assert result.ticket_id == entry_execution.ticket_id
        assert entry_execution.exit_price == _mock_price("EURUSD", close_coid)

        expected_pnl = (
            (entry_execution.exit_price - entry_execution.entry_price)
            * entry_execution.order_intent.computed_lot
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
        assert entry_execution.realized_pnl == expected_pnl

        deal = session.get(MockBrokerDeal, entry_execution.client_order_id)
        assert deal.status == "CLOSED"


def test_partial_close_behaves_as_documented_full_close(sf, redis_client, seeded) -> None:
    adapter = MockExecutionAdapter(sf, redis_client)
    exec_id = _seed_open_entry(
        sf, adapter, seeded, "alice", signal_id="sig-partial-1", position_ref="pos-2"
    )

    result = adapter.place(
        _close_order(
            "coid-partial-1", user_id=seeded["alice"], position_ref="pos-2", action="PARTIAL_CLOSE"
        )
    )
    assert result.status == "ACKNOWLEDGED"

    with sf() as session:
        entry_execution = session.get(Execution, exec_id)
        deal = session.get(MockBrokerDeal, entry_execution.client_order_id)
        assert deal.status == "CLOSED"
        assert entry_execution.exit_price is not None


def test_close_with_no_matching_position_is_rejected_not_silently_opened(
    sf, redis_client, seeded
) -> None:
    adapter = MockExecutionAdapter(sf, redis_client)

    with sf() as session:
        before = session.scalar(select(func.count()).select_from(MockBrokerDeal))

    result = adapter.place(
        _close_order("coid-orphan-close", user_id=seeded["alice"], position_ref="never-opened")
    )

    assert result.status == "REJECTED"
    assert result.raw["reason"] == "no_matching_open_position"

    with sf() as session:
        after = session.scalar(select(func.count()).select_from(MockBrokerDeal))
    assert after == before  # no phantom position was opened


def test_already_closed_position_rejects_a_second_close(sf, redis_client, seeded) -> None:
    adapter = MockExecutionAdapter(sf, redis_client)
    _seed_open_entry(sf, adapter, seeded, "alice", signal_id="sig-close-2", position_ref="pos-3")

    first = adapter.place(_close_order("coid-close-2a", user_id=seeded["alice"], position_ref="pos-3"))
    assert first.status == "ACKNOWLEDGED"

    second = adapter.place(_close_order("coid-close-2b", user_id=seeded["alice"], position_ref="pos-3"))
    assert second.status == "REJECTED"
    assert second.raw["reason"] == "no_matching_open_position"


def test_modify_resolves_without_closing_the_position(sf, redis_client, seeded) -> None:
    adapter = MockExecutionAdapter(sf, redis_client)
    exec_id = _seed_open_entry(
        sf, adapter, seeded, "alice", signal_id="sig-modify-1", position_ref="pos-4"
    )

    result = adapter.place(
        _modify_order("coid-modify-1", user_id=seeded["alice"], position_ref="pos-4")
    )
    assert result.status == "ACKNOWLEDGED"

    with sf() as session:
        entry_execution = session.get(Execution, exec_id)
        deal = session.get(MockBrokerDeal, entry_execution.client_order_id)
        assert deal.status == "OPEN"  # MODIFY does not close the position

    no_match = adapter.place(
        _modify_order("coid-modify-2", user_id=seeded["alice"], position_ref="never-opened")
    )
    assert no_match.status == "REJECTED"
    assert no_match.raw["reason"] == "no_matching_open_position"
