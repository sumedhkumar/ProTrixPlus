"""Fan-out + real entitlement/OFF-policy interaction (PRD 4.3 step 5, 12).

Covers the two PRD MVP acceptance criteria that were previously untestable
because eligibility.py was a placeholder and fanout.py blocked every action
(not just entries) when a strategy was OFF:

* "Turning strategy OFF prevents a subsequent signal from opening a new
  trade" - but per docs/FULL-BUILD-PLAN.md decision #3, does NOT block an
  exit/management signal from closing an already-open position.
* "An expired/non-entitled client does not receive a trade."
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from protrix_contracts.db.models import OrderIntent, Strategy, StrategyAssignment
from sqlalchemy import func, select

from app.adapters.mock import MockExecutionAdapter
from app.fanout import process_signal
from tests.conftest import make_signal

pytestmark = pytest.mark.dbtest


def _set_strategy_active(sf, strategy_id: uuid.UUID, active: bool) -> None:
    with sf() as s:
        strat = s.get(Strategy, strategy_id)
        strat.is_active = active
        s.commit()


def test_strategy_off_blocks_new_entry(sf, redis_client, seeded) -> None:
    _set_strategy_active(sf, seeded["strategy"], False)
    signal_row_id = make_signal(sf, signal_id="off-entry-1", action="BUY")
    adapter = MockExecutionAdapter(sf, redis_client)

    with sf() as session:
        process_signal(session, signal_row_id, adapter)

    with sf() as session:
        assert session.scalar(select(func.count()).select_from(OrderIntent)) == 0


def test_strategy_off_still_allows_exit_to_close_open_position(sf, redis_client, seeded) -> None:
    """OFF must not strand a client's already-open position with no way out."""
    _set_strategy_active(sf, seeded["strategy"], False)
    signal_row_id = make_signal(sf, signal_id="off-close-1", action="CLOSE")
    adapter = MockExecutionAdapter(sf, redis_client)

    with sf() as session:
        process_signal(session, signal_row_id, adapter)

    with sf() as session:
        intents = session.scalars(select(OrderIntent)).all()
        assert len(intents) == 2  # alice + bob, both entitled
        assert {i.command_target for i in intents} == {"CLOSE"}


def test_strategy_on_blocks_nothing(sf, redis_client, seeded) -> None:
    signal_row_id = make_signal(sf, signal_id="on-entry-1", action="BUY")
    adapter = MockExecutionAdapter(sf, redis_client)

    with sf() as session:
        process_signal(session, signal_row_id, adapter)

    with sf() as session:
        assert session.scalar(select(func.count()).select_from(OrderIntent)) == 2


def test_expired_client_gets_no_intent_but_active_client_does(sf, redis_client, seeded) -> None:
    now = datetime.now(UTC)
    with sf() as s:
        alice_assignment = s.scalar(
            select(StrategyAssignment).where(StrategyAssignment.user_id == seeded["alice"])
        )
        alice_assignment.expires_at = now - timedelta(days=1)
        s.commit()

    signal_row_id = make_signal(sf, signal_id="expiry-1", action="BUY")
    adapter = MockExecutionAdapter(sf, redis_client)

    with sf() as session:
        process_signal(session, signal_row_id, adapter)

    with sf() as session:
        intents = session.scalars(select(OrderIntent)).all()
        assert len(intents) == 1
        assert intents[0].user_id == seeded["bob"]


def test_revoked_client_gets_no_intent(sf, redis_client, seeded) -> None:
    with sf() as s:
        bob_assignment = s.scalar(
            select(StrategyAssignment).where(StrategyAssignment.user_id == seeded["bob"])
        )
        bob_assignment.payment_status = "REVOKED"
        s.commit()

    signal_row_id = make_signal(sf, signal_id="revoked-1", action="BUY")
    adapter = MockExecutionAdapter(sf, redis_client)

    with sf() as session:
        process_signal(session, signal_row_id, adapter)

    with sf() as session:
        intents = session.scalars(select(OrderIntent)).all()
        assert len(intents) == 1
        assert intents[0].user_id == seeded["alice"]
