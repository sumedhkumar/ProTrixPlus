"""Shared ORM models = the database contract.

Every invariant that S0 must guarantee has a matching DB-level constraint here:

* ``uq_signals_signal_id`` / ``uq_signals_idempotency_key`` - idempotent
  acceptance of a repeated ``signal_id``.
* ``uq_order_intents_user_id_strategy_id_signal_id_command_target`` - at most one
  order intent per (user, strategy, signal, command_target).
* ``uq_executions_order_intent_id`` / ``uq_executions_client_order_id`` - one
  execution per intent; stable id for reconciliation matching.
* money / lot columns are ``Numeric`` (never float); check constraints keep them
  positive.
* every timestamp is ``timestamptz``; the app always writes UTC.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from protrix_contracts.db.base import Base

# ---------------------------------------------------------------------------
# String-enum vocabularies (also enforced in-DB via CHECK ... IN (...))
# ---------------------------------------------------------------------------


class UserRole(str, enum.Enum):
    USER = "USER"
    SUPER_ADMIN = "SUPER_ADMIN"


class AssignmentStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"


class OutboxStatus(str, enum.Enum):
    PENDING = "PENDING"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"


class IntentStatus(str, enum.Enum):
    CREATED = "CREATED"
    EXECUTING = "EXECUTING"
    SETTLED = "SETTLED"


def _in(column: str, values: type[enum.Enum]) -> str:
    joined = ", ".join(f"'{v.value}'" for v in values)
    return f"{column} IN ({joined})"


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(primary_key=True, default=uuid.uuid4)


def _created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# ---------------------------------------------------------------------------


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint(_in("role", UserRole), name="role_allowed"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default=UserRole.USER.value)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
    created_at: Mapped[datetime] = _created_at()

    assignments: Mapped[list[StrategyAssignment]] = relationship(back_populates="user")


class Strategy(Base):
    __tablename__ = "strategies"
    __table_args__ = (UniqueConstraint("strategy_key", "strategy_version"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    strategy_key: Mapped[str] = mapped_column(String(64), nullable=False)
    strategy_version: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
    created_at: Mapped[datetime] = _created_at()

    assignments: Mapped[list[StrategyAssignment]] = relationship(back_populates="strategy")


class StrategyAssignment(Base):
    __tablename__ = "strategy_assignments"
    __table_args__ = (
        UniqueConstraint("user_id", "strategy_id"),
        CheckConstraint("master_lot > 0", name="master_lot_positive"),
        CheckConstraint("multiplier_min > 0", name="multiplier_min_positive"),
        CheckConstraint("multiplier_min <= multiplier_max", name="multiplier_bounds_ordered"),
        CheckConstraint(
            "multiplier >= multiplier_min AND multiplier <= multiplier_max",
            name="multiplier_within_bounds",
        ),
        CheckConstraint(_in("status", AssignmentStatus), name="status_allowed"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    strategy_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("strategies.id"), nullable=False)

    # Sizing inputs. Stored config is ALWAYS authoritative over any wire value.
    master_lot: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    multiplier: Mapped[Decimal] = mapped_column(Numeric(9, 4), nullable=False, default=1)
    multiplier_min: Mapped[Decimal] = mapped_column(Numeric(9, 4), nullable=False, default=1)
    multiplier_max: Mapped[Decimal] = mapped_column(Numeric(9, 4), nullable=False, default=1)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=AssignmentStatus.ACTIVE.value
    )
    created_at: Mapped[datetime] = _created_at()

    user: Mapped[User] = relationship(back_populates="assignments")
    strategy: Mapped[Strategy] = relationship(back_populates="assignments")


class Signal(Base):
    __tablename__ = "signals"
    __table_args__ = (
        UniqueConstraint("signal_id", name="uq_signals_signal_id"),
        UniqueConstraint("idempotency_key", name="uq_signals_idempotency_key"),
        Index("ix_signals_payload_hash", "payload_hash"),
        Index("ix_signals_strategy", "strategy_key", "strategy_version"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    # Producer-assigned id from the envelope. Basis of idempotent acceptance.
    signal_id: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(256), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(80), nullable=False)

    schema_version: Mapped[str] = mapped_column(String(8), nullable=False)
    strategy_key: Mapped[str] = mapped_column(String(64), nullable=False)
    strategy_version: Mapped[str] = mapped_column(String(32), nullable=False)
    action: Mapped[str] = mapped_column(String(24), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(8), nullable=False)
    position_ref: Mapped[str | None] = mapped_column(String(128))
    close_fraction: Mapped[Decimal | None] = mapped_column(Numeric(9, 4))
    stop_loss: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    take_profit: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))

    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    event_time_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = _created_at()

    intents: Mapped[list[OrderIntent]] = relationship(back_populates="signal")


class Outbox(Base):
    __tablename__ = "outbox"
    __table_args__ = (
        CheckConstraint(_in("status", OutboxStatus), name="status_allowed"),
        Index("ix_outbox_dispatch", "status", "available_at"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    aggregate_type: Mapped[str] = mapped_column(String(48), nullable=False)
    aggregate_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=OutboxStatus.PENDING.value
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()


class OrderIntent(Base):
    __tablename__ = "order_intents"
    __table_args__ = (
        # THE no-duplicate-intent invariant, enforced by the database.
        UniqueConstraint(
            "user_id",
            "strategy_id",
            "signal_id",
            "command_target",
            name="uq_order_intents_user_id_strategy_id_signal_id_command_target",
        ),
        CheckConstraint("computed_lot > 0", name="computed_lot_positive"),
        CheckConstraint(_in("status", IntentStatus), name="status_allowed"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    strategy_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("strategies.id"), nullable=False)
    signal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("signals.id"), nullable=False)
    command_target: Mapped[str] = mapped_column(String(16), nullable=False)

    action: Mapped[str] = mapped_column(String(24), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    computed_lot: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    master_lot: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    multiplier: Mapped[Decimal] = mapped_column(Numeric(9, 4), nullable=False)
    eligibility_status: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=IntentStatus.CREATED.value
    )
    created_at: Mapped[datetime] = _created_at()

    signal: Mapped[Signal] = relationship(back_populates="intents")
    execution: Mapped[Execution | None] = relationship(back_populates="order_intent", uselist=False)


class Execution(Base):
    __tablename__ = "executions"
    __table_args__ = (
        UniqueConstraint("order_intent_id", name="uq_executions_order_intent_id"),
        UniqueConstraint("client_order_id", name="uq_executions_client_order_id"),
        CheckConstraint("reconcile_count >= 0", name="reconcile_count_non_negative"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    order_intent_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("order_intents.id"), nullable=False
    )
    # Stable id we hand the executor; reconciliation matches broker state on this.
    client_order_id: Mapped[str] = mapped_column(String(64), nullable=False)
    adapter: Mapped[str] = mapped_column(String(48), nullable=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False)

    ticket_id: Mapped[str | None] = mapped_column(String(64))
    deal_id: Mapped[str | None] = mapped_column(String(64))
    reconcile_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)

    # Latency segment timestamps (UTC).
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    intent_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    filled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reconciled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Derived latency segments in milliseconds.
    latency_queue_ms: Mapped[int | None] = mapped_column(Integer)
    latency_dispatch_ms: Mapped[int | None] = mapped_column(Integer)
    latency_ack_ms: Mapped[int | None] = mapped_column(Integer)
    latency_fill_ms: Mapped[int | None] = mapped_column(Integer)

    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    order_intent: Mapped[OrderIntent] = relationship(back_populates="execution")


class AuditEvent(Base):
    """Insert-only. UPDATE / DELETE are blocked by a DB rule (see init SQL +
    migration ``0001``)."""

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(48), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(64))
    actor: Mapped[str | None] = mapped_column(String(120))
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = _created_at()


class MockBrokerDeal(Base):
    """MOCK-ONLY durable broker state.

    Lets a simulated "lost executor response" still be reconciled: the mock
    writes the deal here *before* it raises the timeout, so ``sync_positions``
    can report the position exists.
    """

    __tablename__ = "mock_broker_deals"

    client_order_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    ticket_id: Mapped[str] = mapped_column(String(64), nullable=False)
    deal_id: Mapped[str] = mapped_column(String(64), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    volume: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = _created_at()
