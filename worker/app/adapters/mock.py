"""MockExecutionAdapter - deterministic, MetaApi-shaped.

* ``place`` returns deterministic broker ticket / deal ids derived from the
  ``client_order_id`` and records the deal in ``mock_broker_deals`` (durable
  mock broker state).
* A one-shot timeout can be armed by setting the Redis key
  ``mock_exec:arm_timeout``. When armed, ``place`` still records the broker-side
  deal (modelling "request arrived, response lost"), deletes the flag, and
  raises :class:`ExecutionTimeout`. The next reconcile then finds the position.
* ``sync_positions`` returns the recorded deals as broker positions.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime
from decimal import Decimal

from protrix_contracts.db.models import MockBrokerDeal
from redis import Redis
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.base import (
    BrokerClosedDeal,
    BrokerPosition,
    ExecutionTimeout,
    OrderIntentDTO,
    PlaceResult,
)

log = logging.getLogger("worker.adapter.mock")

ARM_TIMEOUT_KEY = "mock_exec:arm_timeout"


def _det_id(prefix: str, seed: str) -> str:
    return prefix + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12].upper()  # noqa: S324


class MockExecutionAdapter:
    name = "mock"

    def __init__(self, session_factory: sessionmaker[Session], redis_client: Redis) -> None:
        self._sf = session_factory
        self._redis = redis_client

    # -- ExecutionAdapter ---------------------------------------------------

    def place(self, order: OrderIntentDTO) -> PlaceResult:
        if order.command_target != "ENTRY":
            return self._place_management(order)

        ticket_id = _det_id("T", order.client_order_id)
        deal_id = _det_id("D", order.client_order_id + ":deal")
        armed = bool(self._redis.delete(ARM_TIMEOUT_KEY))

        # Broker-side state is written whether or not the response makes it back.
        with self._sf() as session:
            session.execute(
                pg_insert(MockBrokerDeal)
                .values(
                    client_order_id=order.client_order_id,
                    ticket_id=ticket_id,
                    deal_id=deal_id,
                    account_ref=order.account_ref,
                    symbol=order.symbol,
                    volume=order.volume,
                    side=order.side,
                    status="OPEN",
                )
                .on_conflict_do_nothing(index_elements=["client_order_id"])
            )
            session.commit()

        if armed:
            log.warning("mock executor: simulated lost response for %s", order.client_order_id)
            raise ExecutionTimeout(f"simulated timeout for {order.client_order_id}")

        return PlaceResult(
            ticket_id=ticket_id,
            deal_id=deal_id,
            status="ACKNOWLEDGED",
            raw={
                "broker": "mock-mt5",
                "ticket": ticket_id,
                "deal": deal_id,
                "account": order.account_ref,
            },
        )

    def _place_management(self, order: OrderIntentDTO) -> PlaceResult:
        """Model a mapped management command without accepting an arbitrary ticket."""
        if not order.broker_position_ref:
            return PlaceResult(
                ticket_id="",
                deal_id="",
                status="REJECTED",
                raw={"reason": "managed_position_not_found", "account_ref": order.account_ref},
            )
        with self._sf() as session:
            position = session.scalar(
                select(MockBrokerDeal).where(
                    MockBrokerDeal.ticket_id == order.broker_position_ref,
                    MockBrokerDeal.account_ref == order.account_ref,
                )
            )
            if position is None or position.status != "OPEN":
                return PlaceResult(
                    ticket_id="",
                    deal_id="",
                    status="REJECTED",
                    raw={"reason": "managed_position_not_open", "account_ref": order.account_ref},
                )
            ticket_id = _det_id("T", order.client_order_id)
            deal_id = _det_id("D", order.client_order_id + ":deal")
            action = order.action.upper()
            status = "MODIFIED" if action == "MODIFY_SLTP" else "CLOSED"
            volume = position.volume
            if action == "PARTIAL_CLOSE" and order.close_fraction is not None:
                volume = Decimal(position.volume) * order.close_fraction
            session.add(
                MockBrokerDeal(
                    client_order_id=order.client_order_id,
                    ticket_id=ticket_id,
                    deal_id=deal_id,
                    account_ref=order.account_ref,
                    symbol=position.symbol,
                    volume=volume,
                    side=position.side,
                    status=status,
                )
            )
            session.commit()
        return PlaceResult(
            ticket_id=ticket_id,
            deal_id=deal_id,
            status="ACKNOWLEDGED",
            raw={"broker": "mock-mt5", "account": order.account_ref, "management": action},
        )

    def sync_positions(self, account_ref: str) -> list[BrokerPosition]:
        with self._sf() as session:
            rows = session.scalars(
                select(MockBrokerDeal).where(MockBrokerDeal.account_ref == account_ref)
            ).all()
        return [
            BrokerPosition(
                client_order_id=r.client_order_id,
                ticket_id=r.ticket_id,
                deal_id=r.deal_id,
                symbol=r.symbol,
                volume=Decimal(r.volume),
                side="SELL" if r.side == "SELL" else "BUY",
                status=r.status,
            )
            for r in rows
        ]

    def sync_closed_deals(self, account_ref: str, since: datetime) -> list[BrokerClosedDeal]:
        """Expose deterministic mock exits; mock PnL is intentionally zero."""
        with self._sf() as session:
            rows = session.scalars(
                select(MockBrokerDeal).where(
                    MockBrokerDeal.account_ref == account_ref,
                    MockBrokerDeal.status == "CLOSED",
                    MockBrokerDeal.created_at >= since,
                )
            ).all()
        return [
            BrokerClosedDeal(
                deal_id=row.deal_id,
                position_ref=row.ticket_id,
                closed_at=row.created_at.astimezone(UTC),
                net_realized_pnl=Decimal("0"),
            )
            for row in rows
        ]

    # -- test / simulator helper -----------------------------------------------

    def arm_timeout_once(self) -> None:
        self._redis.set(ARM_TIMEOUT_KEY, "1")
