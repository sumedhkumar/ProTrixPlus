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
    # A brand-new admin grant starts here - not eligible for fan-out
    # (worker/app/fanout.py only admits ACTIVE) until the client completes
    # the setup wizard (sizing + MT5 connection) and explicitly confirms the
    # risk disclosure via POST /me/assignments/{id}/confirm-start.
    SETUP_INCOMPLETE = "SETUP_INCOMPLETE"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"


class Mt5ConnectionStatus(str, enum.Enum):
    """PRD 4.1 step 3: Connected / Disconnected / Error, plus NOT_CONFIGURED
    for before a client has submitted connection details, and PENDING for
    submitted-but-never-actually-checked (true today: no real MetaApi
    credentials are wired in yet, see docs/FULL-BUILD-PLAN.md Phase 3)."""

    NOT_CONFIGURED = "NOT_CONFIGURED"
    PENDING = "PENDING"
    CONNECTED = "CONNECTED"
    DISCONNECTED = "DISCONNECTED"
    ERROR = "ERROR"


class PaymentStatus(str, enum.Enum):
    """Entitlement gate, independent of ``AssignmentStatus``.

    ``AssignmentStatus`` is the admin's coarse per-client enable/disable
    switch. ``PaymentStatus`` + ``expires_at`` together are the entitlement
    check: a client can be ACTIVE (enabled) but still ineligible because
    payment was REVOKED or the entitlement has expired.
    """

    GRANTED = "GRANTED"
    REVOKED = "REVOKED"


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
    # NULL for seeded/dev-only users (they can only ever use /dev/login).
    # Never a plaintext password - PBKDF2-HMAC-SHA256, salted, see app/auth.py.
    password_hash: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = _created_at()

    assignments: Mapped[list[StrategyAssignment]] = relationship(back_populates="user")


class Strategy(Base):
    __tablename__ = "strategies"
    __table_args__ = (
        UniqueConstraint("strategy_key", "strategy_version"),
        CheckConstraint("price IS NULL OR price >= 0", name="price_non_negative"),
        CheckConstraint(
            "profit_share_percent IS NULL "
            "OR (profit_share_percent >= 0 AND profit_share_percent <= 100)",
            name="profit_share_percent_in_range",
        ),
        CheckConstraint("base_lot IS NULL OR base_lot > 0", name="base_lot_positive"),
        CheckConstraint(
            "win_rate IS NULL OR (win_rate >= 0 AND win_rate <= 100)", name="win_rate_in_range"
        ),
        CheckConstraint(
            "max_drawdown IS NULL OR (max_drawdown >= 0 AND max_drawdown <= 100)",
            name="max_drawdown_in_range",
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    strategy_key: Mapped[str] = mapped_column(String(64), nullable=False)
    strategy_version: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)

    # Catalog fields (PRD 5.3: admin-managed strategy catalog).
    description: Mapped[str | None] = mapped_column(Text)
    symbol: Mapped[str | None] = mapped_column(String(32))
    timeframe: Mapped[str | None] = mapped_column(String(8))
    price: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    profit_share_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    base_lot: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))

    # Marketing/catalog-display fields. `description` above is the long
    # description; `description_short` is the one-liner shown on the catalog
    # card. Neither win_rate nor max_drawdown feed sizing/eligibility logic -
    # display only.
    win_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    max_drawdown: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    description_short: Mapped[str | None] = mapped_column(String(240))

    created_at: Mapped[datetime] = _created_at()

    assignments: Mapped[list[StrategyAssignment]] = relationship(back_populates="strategy")
    alerts: Mapped[list[Alert]] = relationship(back_populates="strategy")


class Alert(Base):
    """An admin-authored TradingView alert config (PRD Feature 1).

    TradingView has no API that pushes "alert created/edited" events - only
    live BUY/SELL webhook signals arrive (see ``Signal`` below). So this is
    captured the other way round from how it might first sound: the admin
    defines the alert's symbol/lot size/timeframe here, in ProTrixPlus, then
    pastes the resulting config into TradingView's own alert dialog. One or
    more Alerts are bundled into a Strategy (Feature 2) for catalog display -
    bundling never changes how an incoming signal is matched to a strategy
    (still ``Signal.strategy_key``/``strategy_version``, unaffected by this
    table). Every field change is diffed and recorded as an ``AuditEvent``
    (entity_type="alert") by the service layer - this table itself has no
    changelog columns.
    """

    __tablename__ = "alerts"
    __table_args__ = (
        CheckConstraint("lot_size > 0", name="alert_lot_size_positive"),
        Index("ix_alerts_strategy_id", "strategy_id"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    strategy_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("strategies.id", ondelete="SET NULL")
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    lot_size: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(8), nullable=False)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    strategy: Mapped[Strategy | None] = relationship(back_populates="alerts")


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
        CheckConstraint(_in("payment_status", PaymentStatus), name="payment_status_allowed"),
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

    # Entitlement (PRD 5.3/5.8). Distinct from `status` above: an assignment
    # can be admin-ACTIVE but still ineligible if not GRANTED or expired.
    # MVP payment workflow is admin-granted (no payment gateway) - see
    # docs/FULL-BUILD-PLAN.md decision #4.
    purchased_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payment_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=PaymentStatus.GRANTED.value
    )

    # Setup-wizard risk gate (Setup Wizard step 3): set only by
    # marketplace.confirm_start, once, when the client explicitly clicks
    # through the risk-disclosure confirmation. Never set by an admin grant.
    confirmed_risk_disclosure: Mapped[bool] = mapped_column(nullable=False, default=False)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

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

    # P&L attribution (PRD 5.6). Populated once the position is closed;
    # NULL while the position is still open.
    entry_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    exit_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    realized_pnl: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))

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


class Mt5Connection(Base):
    """One connected MT5 account per client for MVP (PRD 3.1, 4.1, 5.2).

    Deliberately never stores an MT5 password/investor password anywhere -
    that must go through the real CredentialVault (api/app/vault/, still a
    stub as of this table's introduction) once it exists, never a plain
    column here. ``login`` (the MT5 account number) is not itself a secret.
    """

    __tablename__ = "mt5_connections"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_mt5_connections_user_id"),
        CheckConstraint(_in("status", Mt5ConnectionStatus), name="status_allowed"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    broker_server: Mapped[str] = mapped_column(String(120), nullable=False)
    login: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default=Mt5ConnectionStatus.NOT_CONFIGURED.value
    )
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    # Set by an admin once this client's MT5 account has been provisioned in
    # MetaApi's own dashboard (never entered by the client - MetaApi hands
    # these back after account creation, they aren't secrets). Both required
    # together before MetaApiExecutionAdapter will route a real order here.
    metaapi_account_id: Mapped[str | None] = mapped_column(String(64))
    metaapi_region: Mapped[str | None] = mapped_column(String(32))
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
