"""Per-user account routing for the metaapi adapter (worker/app/execution.py).

Unlike ``mock``/the native ``mt5`` adapter (single synthetic/single-terminal
account), ``metaapi`` is multi-tenant: every user needs their *own* real
MetaApi account attached via ``Mt5Connection`` before a signal for them can
dispatch anywhere. These tests exercise that gate directly against a fake
adapter (no real HTTP) - the real MetaApiExecutionAdapter's own HTTP behavior
is covered separately in test_metaapi_adapter.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

import pytest
from protrix_contracts.db.models import Mt5Connection, OrderIntent, Signal
from protrix_contracts.lifecycle import ExecutionState
from sqlalchemy import select

from app.adapters.base import BrokerPosition, OrderIntentDTO, PlaceResult
from app.execution import drive_new_execution
from tests.conftest import make_signal

pytestmark = pytest.mark.dbtest


@dataclass
class _RecordingAdapter:
    """Bare-bones fake satisfying the ExecutionAdapter Protocol - records the
    account_ref it was actually called with, so the test can assert routing
    without any real network access."""

    name: str
    placed_with: list[str] = field(default_factory=list)

    def place(self, order: OrderIntentDTO) -> PlaceResult:
        self.placed_with.append(order.account_ref)
        return PlaceResult(
            ticket_id="T1", deal_id="D1", status="ACKNOWLEDGED", raw={"account": order.account_ref}
        )

    def sync_positions(self, account_ref: str) -> list[BrokerPosition]:  # pragma: no cover
        return []


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


@pytest.fixture
def ids(sf, seeded):
    make_signal(sf)
    return seeded


def test_mock_adapter_is_unaffected_by_missing_mt5_connection(sf, ids) -> None:
    """Regression guard: adding metaapi routing must never require every
    mock-adapter user (i.e. every existing demo account) to suddenly have an
    Mt5Connection row."""
    adapter = _RecordingAdapter(name="mock")
    with sf() as session:
        intent = _make_intent(session, ids, "alice")
        session.commit()
        execution = drive_new_execution(session, intent, adapter)
        session.commit()
        assert execution.state == ExecutionState.FILLED.value
    assert adapter.placed_with == [f"acct-{ids['alice']}"]


def test_metaapi_rejects_cleanly_with_no_mt5_connection_at_all(sf, ids) -> None:
    adapter = _RecordingAdapter(name="metaapi")
    with sf() as session:
        intent = _make_intent(session, ids, "alice")
        session.commit()
        execution = drive_new_execution(session, intent, adapter)
        session.commit()
        assert execution.state == ExecutionState.REJECTED.value
        assert execution.last_error is not None
        assert "metaapi" in execution.last_error
    assert adapter.placed_with == []  # never dispatched - nowhere to send it


def test_metaapi_rejects_cleanly_when_connection_exists_but_metaapi_id_unset(sf, ids) -> None:
    """A client can have set their broker_server/login (self-service) without
    an admin having attached the MetaApi side yet - must still reject, not
    error."""
    adapter = _RecordingAdapter(name="metaapi")
    with sf() as session:
        session.add(
            Mt5Connection(user_id=ids["alice"], broker_server="ICMarketsSC-Demo", login="123")
        )
        intent = _make_intent(session, ids, "alice")
        session.commit()
        execution = drive_new_execution(session, intent, adapter)
        session.commit()
        assert execution.state == ExecutionState.REJECTED.value
    assert adapter.placed_with == []


def test_metaapi_routes_to_the_right_users_own_account(sf, ids) -> None:
    adapter = _RecordingAdapter(name="metaapi")
    with sf() as session:
        session.add(
            Mt5Connection(
                user_id=ids["alice"],
                broker_server="MetaQuotes-Demo",
                login="112861630",
                metaapi_account_id="b6b65caf-5b94-476e-8e7b-889b819f4f97",
                metaapi_region="london",
            )
        )
        intent = _make_intent(session, ids, "alice")
        session.commit()
        execution = drive_new_execution(session, intent, adapter)
        session.commit()
        assert execution.state == ExecutionState.FILLED.value
    assert adapter.placed_with == ["london:b6b65caf-5b94-476e-8e7b-889b819f4f97"]


def test_metaapi_never_cross_routes_between_two_users(sf, ids) -> None:
    """The exact bug that would silently place one client's trade on
    another's account - must never happen."""
    adapter = _RecordingAdapter(name="metaapi")
    with sf() as session:
        session.add(
            Mt5Connection(
                user_id=ids["alice"],
                broker_server="MetaQuotes-Demo",
                login="111",
                metaapi_account_id="alice-account-id",
                metaapi_region="london",
            )
        )
        session.add(
            Mt5Connection(
                user_id=ids["bob"],
                broker_server="MetaQuotes-Demo",
                login="222",
                metaapi_account_id="bob-account-id",
                metaapi_region="new-york",
            )
        )
        intent_a = _make_intent(session, ids, "alice")
        intent_b = _make_intent(session, ids, "bob")
        session.commit()
        drive_new_execution(session, intent_a, adapter)
        drive_new_execution(session, intent_b, adapter)
        session.commit()

    assert adapter.placed_with == [
        "london:alice-account-id",
        "new-york:bob-account-id",
    ]
