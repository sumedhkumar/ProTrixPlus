"""MockExecutionAdapter - deterministic, MetaApi-shaped.

* ``place`` returns deterministic broker ticket / deal ids derived from the
  ``client_order_id`` and records the deal in ``mock_broker_deals`` (durable
  mock broker state).
* A one-shot timeout can be armed by setting the Redis key
  ``mock_exec:arm_timeout``. When armed, ``place`` still records the broker-side
  deal (modelling "request arrived, response lost"), deletes the flag, and
  raises :class:`ExecutionTimeout`. The next reconcile then finds the position.
* ``sync_positions`` returns the recorded deals as broker positions.
* CLOSE/PARTIAL_CLOSE/MODIFY_SLTP/EMERGENCY_CLOSE resolve against the open
  position matching (user, strategy, ``position_ref``) - see
  :func:`_find_open_position`. No match -> a clean rejection, never a
  phantom new position. PARTIAL_CLOSE performs a full close in this MVP
  (documented simplification: nothing in the schema tracks partial-fill
  remaining volume yet).
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from decimal import ROUND_HALF_EVEN, Decimal

from protrix_contracts.db.models import Execution, MockBrokerDeal, OrderIntent, Signal
from protrix_contracts.money import MONEY_QUANT
from redis import Redis
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.base import (
    BrokerPosition,
    ExecutionTimeout,
    OrderIntentDTO,
    PlaceResult,
)

log = logging.getLogger("worker.adapter.mock")

ARM_TIMEOUT_KEY = "mock_exec:arm_timeout"
_CLOSE_TARGETS = {"CLOSE", "EMERGENCY"}
_PNL_QUANT = Decimal("0.01")

# Deterministic fake reference prices, close enough to be plausible in a demo.
# Symbols not listed fall back to _DEFAULT_BASE_PRICE.
_BASE_PRICES: dict[str, Decimal] = {
    "EURUSD": Decimal("1.08000"),
    "GBPUSD": Decimal("1.27000"),
    "XAUUSD": Decimal("2400.00"),
}
_DEFAULT_BASE_PRICE = Decimal("100.00000")


def _det_id(prefix: str, seed: str) -> str:
    return prefix + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12].upper()  # noqa: S324


def _mock_price(symbol: str, seed: str) -> Decimal:
    """Deterministic fake price for (symbol, seed), +/-0.5% around a fixed
    base - same hash-of-id idiom as :func:`_det_id`, just mapped to a decimal
    range instead of a hex id."""
    base = _BASE_PRICES.get(symbol.upper(), _DEFAULT_BASE_PRICE)
    digest = hashlib.sha1(f"{symbol}:{seed}".encode("utf-8")).hexdigest()  # noqa: S324
    raw = int(digest[:6], 16)
    fraction = (Decimal(raw) / Decimal(0xFFFFFF)) - Decimal("0.5")  # in [-0.5, 0.5]
    offset = base * fraction * Decimal("0.01")  # up to +/-0.5% of base
    return (base + offset).quantize(MONEY_QUANT, rounding=ROUND_HALF_EVEN)


class MockExecutionAdapter:
    name = "mock"

    def __init__(self, session_factory: sessionmaker[Session], redis_client: Redis) -> None:
        self._sf = session_factory
        self._redis = redis_client

    # -- ExecutionAdapter ---------------------------------------------------

    def place(self, order: OrderIntentDTO) -> PlaceResult:
        if order.command_target == "ENTRY":
            return self._place_entry(order)
        if order.command_target in _CLOSE_TARGETS:
            return self._place_close(order)
        if order.command_target == "MODIFY":
            return self._place_modify(order)
        return self._rejected("unknown_command_target", order)  # pragma: no cover - defensive

    def sync_positions(self, account_ref: str) -> list[BrokerPosition]:
        with self._sf() as session:
            rows = session.scalars(select(MockBrokerDeal)).all()
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

    # -- entry / close / modify ----------------------------------------------

    def _place_entry(self, order: OrderIntentDTO) -> PlaceResult:
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

        entry_price = _mock_price(order.symbol, order.client_order_id)
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
            entry_price=entry_price,
        )

    def _place_close(self, order: OrderIntentDTO) -> PlaceResult:
        if order.action.upper() == "PARTIAL_CLOSE":
            log.info(
                "mock executor: PARTIAL_CLOSE treated as a full close for %s "
                "(no partial-fill tracking in this MVP)",
                order.client_order_id,
            )

        with self._sf() as session:
            match = _find_open_position(session, order)
            if match is None:
                return self._rejected("no_matching_open_position", order)
            deal, matched_execution = match

            deal.status = "CLOSED"
            exit_price = _mock_price(order.symbol, order.client_order_id)
            matched_execution.exit_price = exit_price
            if matched_execution.entry_price is not None:
                matched_execution.realized_pnl = _realized_pnl(
                    entry_price=matched_execution.entry_price,
                    exit_price=exit_price,
                    volume=matched_execution.order_intent.computed_lot,
                    side=matched_execution.order_intent.action,
                )
            session.commit()
            ticket_id, deal_id = deal.ticket_id, deal.deal_id

        return PlaceResult(
            ticket_id=ticket_id,
            deal_id=deal_id,
            status="ACKNOWLEDGED",
            raw={"broker": "mock-mt5", "closed": ticket_id, "account": order.account_ref},
        )

    def _place_modify(self, order: OrderIntentDTO) -> PlaceResult:
        # The mock deal has no SL/TP columns to persist a new value into; this
        # only proves the position resolves, which is what MODIFY_SLTP needs
        # before it can do anything real.
        with self._sf() as session:
            match = _find_open_position(session, order)
            if match is None:
                return self._rejected("no_matching_open_position", order)
            deal, _matched_execution = match
            ticket_id, deal_id = deal.ticket_id, deal.deal_id

        return PlaceResult(
            ticket_id=ticket_id,
            deal_id=deal_id,
            status="ACKNOWLEDGED",
            raw={"broker": "mock-mt5", "modified": ticket_id, "account": order.account_ref},
        )

    def _rejected(self, reason: str, order: OrderIntentDTO) -> PlaceResult:
        return PlaceResult(
            ticket_id="",
            deal_id="",
            status="REJECTED",
            raw={"reason": reason, "account_ref": order.account_ref},
        )

    # -- test / simulator helper -----------------------------------------------

    def arm_timeout_once(self) -> None:
        self._redis.set(ARM_TIMEOUT_KEY, "1")


def _find_open_position(
    session: Session, order: OrderIntentDTO
) -> tuple[MockBrokerDeal, Execution] | None:
    """The open ENTRY position this CLOSE/MODIFY targets: same user, same
    strategy, same ``position_ref``, still OPEN on the mock broker."""
    if not (order.user_id and order.strategy_key and order.strategy_version and order.position_ref):
        return None
    row = session.execute(
        select(MockBrokerDeal, Execution)
        .join(Execution, Execution.client_order_id == MockBrokerDeal.client_order_id)
        .join(OrderIntent, OrderIntent.id == Execution.order_intent_id)
        .join(Signal, Signal.id == OrderIntent.signal_id)
        .where(
            OrderIntent.user_id == uuid.UUID(order.user_id),
            OrderIntent.command_target == "ENTRY",
            Signal.strategy_key == order.strategy_key,
            Signal.strategy_version == order.strategy_version,
            Signal.position_ref == order.position_ref,
            MockBrokerDeal.status == "OPEN",
        )
        .order_by(Execution.created_at.desc())
        .limit(1)
    ).first()
    return (row[0], row[1]) if row is not None else None


def _realized_pnl(*, entry_price: Decimal, exit_price: Decimal, volume: Decimal, side: str) -> Decimal:
    direction = 1 if side.upper() == "BUY" else -1
    pnl = (exit_price - entry_price) * volume * direction
    return pnl.quantize(_PNL_QUANT, rounding=ROUND_HALF_EVEN)
