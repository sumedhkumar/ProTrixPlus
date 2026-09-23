"""A brand-new admin grant defaults to SETUP_INCOMPLETE (api/app/services/
marketplace.py's admin_grant_entitlement) and must not fan out until the
client completes the setup wizard and flips it to ACTIVE via confirm_start.
fanout.py's eligible-pairs query already filters status == "ACTIVE" only -
this is a regression test for that gate, not a code change.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from protrix_contracts.db.models import Execution, OrderIntent, StrategyAssignment, User
from sqlalchemy import func, select

from app.adapters.mock import MockExecutionAdapter
from app.fanout import process_signal
from tests.conftest import make_signal

pytestmark = pytest.mark.dbtest


def test_setup_incomplete_assignment_does_not_fan_out(sf, redis_client, seeded) -> None:
    with sf() as s:
        carol = User(email="carol@example.test", display_name="Carol", role="USER")
        s.add(carol)
        s.flush()
        carol_id = carol.id
        s.add(
            StrategyAssignment(
                user_id=carol_id,
                strategy_id=seeded["strategy"],
                master_lot=Decimal("1.00"),
                multiplier=Decimal("1.0000"),
                multiplier_min=Decimal("0.5000"),
                multiplier_max=Decimal("2.0000"),
                status="SETUP_INCOMPLETE",
            )
        )
        s.commit()

    signal_row_id = make_signal(sf)
    adapter = MockExecutionAdapter(sf, redis_client)

    with sf() as session:
        process_signal(session, signal_row_id, adapter)

    with sf() as session:
        # Only alice + bob (both ACTIVE via the `seeded` fixture) - carol's
        # SETUP_INCOMPLETE assignment must be excluded.
        assert session.scalar(select(func.count()).select_from(OrderIntent)) == 2
        assert session.scalar(select(func.count()).select_from(Execution)) == 2
        intent_user_ids = set(session.scalars(select(OrderIntent.user_id)).all())
        assert carol_id not in intent_user_ids


def test_pending_approval_assignment_does_not_fan_out(sf, redis_client, seeded) -> None:
    """A client self-subscribing (api/app/services/marketplace.py's
    self_subscribe) starts even earlier than SETUP_INCOMPLETE - locked until
    an admin confirms payment. Must not fan out either."""
    with sf() as s:
        dave = User(email="dave@example.test", display_name="Dave", role="USER")
        s.add(dave)
        s.flush()
        dave_id = dave.id
        s.add(
            StrategyAssignment(
                user_id=dave_id,
                strategy_id=seeded["strategy"],
                master_lot=Decimal("1.00"),
                multiplier=Decimal("1.0000"),
                multiplier_min=Decimal("0.5000"),
                multiplier_max=Decimal("2.0000"),
                status="PENDING_APPROVAL",
            )
        )
        s.commit()

    signal_row_id = make_signal(sf, signal_id="sig-w-2")
    adapter = MockExecutionAdapter(sf, redis_client)

    with sf() as session:
        process_signal(session, signal_row_id, adapter)

    with sf() as session:
        intent_user_ids = set(session.scalars(select(OrderIntent.user_id)).all())
        assert dave_id not in intent_user_ids
