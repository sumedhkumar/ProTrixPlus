"""MockExecutionAdapter: deterministic ids, durable mock broker state, one-shot
timeout that still leaves a reconcilable position."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.adapters.base import ExecutionTimeout, OrderIntentDTO
from app.adapters.mock import MockExecutionAdapter

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


def test_place_is_deterministic_and_records_broker_state(sf, redis_client, clean_db) -> None:
    adapter = MockExecutionAdapter(sf, redis_client)
    r1 = adapter.place(_order("coid-1"))
    r2 = adapter.place(_order("coid-1"))
    assert (r1.ticket_id, r1.deal_id) == (r2.ticket_id, r2.deal_id)
    assert r1.status == "ACKNOWLEDGED"

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
