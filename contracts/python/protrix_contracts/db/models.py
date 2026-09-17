"""Shared ORM models = the database contract.

Every invariant that S0 must guarantee has a matching DB-level constraint here:

* ``uq_signals_signal_id`` / ``uq_signals_idempotency_key`` - idempotent
  acceptance of a repeated ``signal_id``.
* ``uq_order_intents_signal_op_key`` - at most one order intent per deterministic
  signal operation key.
* ``uq_executions_order_intent_id`` / ``uq_executions_client_order_id`` - one
  execution per intent; stable id for reconciliation matching.
* rent settlements and ledger entries are immutable, idempotent records. A
  settlement can have at most one rent charge entry.
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
    text,
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


class SettlementCadence(str, enum.Enum):
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"


class RentLedgerEntryType(str, enum.Enum):
    TOP_UP = "TOP_UP"
    RENT_CHARGE = "RENT_CHARGE"
    ADJUSTMENT = "ADJUSTMENT"
    REVERSAL = "REVERSAL"


class EnrollmentStatus(str, enum.Enum):
    """Lifecycle of one user's access to one marketplace strategy."""

    CREDENTIALS_REQUIRED = "CREDENTIALS_REQUIRED"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    EXPIRED = "EXPIRED"
    DISABLED = "DISABLED"


class PaymentStatus(str, enum.Enum):
    PENDING = "PENDING"
    PAID = "PAID"
    FAILED = "FAILED"
    REFUND_REVIEW = "REFUND_REVIEW"


class PaymentPurpose(str, enum.Enum):
    STRATEGY_PURCHASE = "STRATEGY_PURCHASE"
    WALLET_TOP_UP = "WALLET_TOP_UP"


class PurchaseSource(str, enum.Enum):
    RAZORPAY = "RAZORPAY"
    ADMIN = "ADMIN"


class AccountCategory(str, enum.Enum):
    DEMO = "DEMO"
    LIVE = "LIVE"


class AccountTransport(str, enum.Enum):
    MOCK = "MOCK"
    NATIVE_MT5 = "NATIVE_MT5"
    METAAPI = "METAAPI"


class TradingAccountStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"


class SubscriptionStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    DISABLED = "DISABLED"


class ManagedPositionStatus(str, enum.Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


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
    trading_account: Mapped[TradingAccount | None] = relationship(
        back_populates="user", uselist=False
    )
    settlements: Mapped[list[Settlement]] = relationship(back_populates="user")
    rent_ledger_entries: Mapped[list[RentLedgerEntry]] = relationship(back_populates="user")


class TradingAccount(Base):
    """The single permitted execution account for a user in the first release.

    ``credential_key_ref`` is an opaque vault/local-profile reference, never a
    login, password, token, or other secret. The selected transport describes
    the intended execution route; switching to MetaApi later does not move any
    sizing or risk decision outside Protrixplus.
    """

    __tablename__ = "trading_accounts"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_trading_accounts_user_id"),
        CheckConstraint(_in("category", AccountCategory), name="category_allowed"),
        CheckConstraint(_in("transport", AccountTransport), name="transport_allowed"),
        CheckConstraint(_in("status", TradingAccountStatus), name="status_allowed"),
    )

    # Reusing the user's UUID makes the one-to-one migration deterministic and
    # lets old intent rows be backfilled without generating database UUIDs.
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    provider_name: Mapped[str] = mapped_column(String(120), nullable=False)
    server_identifier: Mapped[str | None] = mapped_column(String(160))
    category: Mapped[str] = mapped_column(String(12), nullable=False)
    transport: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    external_account_ref: Mapped[str | None] = mapped_column(String(160))
    credential_key_ref: Mapped[str | None] = mapped_column(String(160))
    worker_adapter: Mapped[str | None] = mapped_column(String(32))
    worker_name: Mapped[str | None] = mapped_column(String(120))
    worker_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created_at()

    user: Mapped[User] = relationship(back_populates="trading_account")


class Subscription(Base):
    """One current access subscription per user for the MVP."""

    __tablename__ = "subscriptions"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_subscriptions_user_id"),
        CheckConstraint(_in("status", SubscriptionStatus), name="status_allowed"),
        CheckConstraint("ends_at > starts_at", name="period_ordered"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    plan_code: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = _created_at()


class TradingControl(Base):
    """Explicit admin and safety blocks, kept separate from the display state."""

    __tablename__ = "trading_controls"
    __table_args__ = (UniqueConstraint("user_id", name="uq_trading_controls_user_id"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    admin_suspended: Mapped[bool] = mapped_column(nullable=False, default=False)
    risk_blocked: Mapped[bool] = mapped_column(nullable=False, default=False)
    kill_switch: Mapped[bool] = mapped_column(nullable=False, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class RiskProfile(Base):
    """Stored backend risk limits. Webhook payloads never override these values."""

    __tablename__ = "risk_profiles"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_risk_profiles_user_id"),
        CheckConstraint("max_lot > 0", name="max_lot_positive"),
        CheckConstraint("max_open_trades > 0", name="max_open_trades_positive"),
        CheckConstraint("max_daily_loss >= 0", name="max_daily_loss_non_negative"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    max_lot: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    max_open_trades: Mapped[int] = mapped_column(Integer, nullable=False)
    max_daily_loss: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    allowed_symbols: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ManagedPosition(Base):
    """Immutable attribution key plus mutable remaining managed volume."""

    __tablename__ = "managed_positions"
    __table_args__ = (
        UniqueConstraint("entry_execution_id", name="uq_managed_positions_entry_execution_id"),
        UniqueConstraint(
            "user_id", "strategy_id", "source_position_ref", name="uq_managed_positions_source_ref"
        ),
        CheckConstraint(_in("status", ManagedPositionStatus), name="status_allowed"),
        CheckConstraint("initial_volume > 0", name="initial_volume_positive"),
        CheckConstraint("remaining_volume >= 0", name="remaining_volume_non_negative"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    strategy_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("strategies.id"), nullable=False)
    entry_execution_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("executions.id"), nullable=False
    )
    source_position_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    broker_position_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    initial_volume: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    remaining_volume: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


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


class StrategyOffer(Base):
    """Published marketplace terms for a strategy.

    Purchases snapshot these values so later price edits never rewrite history.
    """

    __tablename__ = "strategy_offers"
    __table_args__ = (
        UniqueConstraint("strategy_id", name="uq_strategy_offers_strategy_id"),
        CheckConstraint("price_usd > 0", name="price_usd_positive"),
        CheckConstraint("platform_fee_usd >= 0", name="platform_fee_usd_non_negative"),
        CheckConstraint("escrow_credit_usd >= 0", name="escrow_credit_usd_non_negative"),
        CheckConstraint(
            "platform_fee_usd + escrow_credit_usd = price_usd", name="offer_split_matches_price"
        ),
        CheckConstraint("duration_days > 0", name="duration_days_positive"),
        CheckConstraint("minimum_wallet_usd >= 0", name="minimum_wallet_usd_non_negative"),
        CheckConstraint(
            "profit_share_rate >= 0 AND profit_share_rate <= 1",
            name="profit_share_rate_between_zero_and_one",
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    strategy_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("strategies.id"), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    price_usd: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    platform_fee_usd: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    escrow_credit_usd: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    duration_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    minimum_wallet_usd: Mapped[Decimal] = mapped_column(
        Numeric(18, 8), nullable=False, default=Decimal("10.00")
    )
    profit_share_rate: Mapped[Decimal] = mapped_column(
        Numeric(9, 6), nullable=False, default=Decimal("0.10")
    )
    is_published: Mapped[bool] = mapped_column(nullable=False, default=False)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class StrategyEnrollment(Base):
    """One user's isolated strategy runtime and wallet boundary."""

    __tablename__ = "strategy_enrollments"
    __table_args__ = (
        UniqueConstraint("user_id", "strategy_id", name="uq_strategy_enrollments_user_strategy"),
        CheckConstraint(_in("status", EnrollmentStatus), name="status_allowed"),
        CheckConstraint("minimum_wallet_usd >= 0", name="minimum_wallet_usd_non_negative"),
        CheckConstraint(
            "profit_share_rate >= 0 AND profit_share_rate <= 1",
            name="profit_share_rate_between_zero_and_one",
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    strategy_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("strategies.id"), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=EnrollmentStatus.CREDENTIALS_REQUIRED.value
    )
    minimum_wallet_usd: Mapped[Decimal] = mapped_column(
        Numeric(18, 8), nullable=False, default=Decimal("10.00")
    )
    profit_share_rate: Mapped[Decimal] = mapped_column(
        Numeric(9, 6), nullable=False, default=Decimal("0.10")
    )
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class EnrollmentAccount(Base):
    """Dedicated execution-account metadata for a strategy enrollment.

    ``credential_key_ref`` is an opaque vault reference only. Plaintext MT5
    credentials never enter the application database.
    """

    __tablename__ = "enrollment_accounts"
    __table_args__ = (
        UniqueConstraint("enrollment_id", name="uq_enrollment_accounts_enrollment_id"),
        UniqueConstraint(
            "server_identifier",
            "broker_login",
            name="uq_enrollment_accounts_server_broker_login",
        ),
        Index(
            "uq_enrollment_accounts_external_account_ref",
            "external_account_ref",
            unique=True,
            postgresql_where=text("external_account_ref IS NOT NULL"),
        ),
        CheckConstraint(_in("category", AccountCategory), name="category_allowed"),
        CheckConstraint(_in("transport", AccountTransport), name="transport_allowed"),
        CheckConstraint(_in("status", TradingAccountStatus), name="status_allowed"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    enrollment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("strategy_enrollments.id"), nullable=False
    )
    provider_name: Mapped[str] = mapped_column(String(120), nullable=False)
    server_identifier: Mapped[str | None] = mapped_column(String(160))
    category: Mapped[str] = mapped_column(
        String(12), nullable=False, default=AccountCategory.DEMO.value
    )
    transport: Mapped[str] = mapped_column(
        String(16), nullable=False, default=AccountTransport.MOCK.value
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=TradingAccountStatus.DISABLED.value
    )
    external_account_ref: Mapped[str | None] = mapped_column(String(160))
    # MT5 login is an account identifier, not a secret. Passwords remain only
    # in the vault; retaining this identifier lets workers prove route isolation.
    broker_login: Mapped[str | None] = mapped_column(String(80))
    credential_key_ref: Mapped[str | None] = mapped_column(String(160))
    worker_adapter: Mapped[str | None] = mapped_column(String(32))
    worker_name: Mapped[str | None] = mapped_column(String(120))
    worker_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class StrategyPurchase(Base):
    """Immutable 30-day entitlement purchase or administrator activation."""

    __tablename__ = "strategy_purchases"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_strategy_purchases_idempotency_key"),
        UniqueConstraint("razorpay_order_id", name="uq_strategy_purchases_razorpay_order_id"),
        CheckConstraint(_in("source", PurchaseSource), name="source_allowed"),
        CheckConstraint(_in("status", PaymentStatus), name="status_allowed"),
        CheckConstraint("price_usd > 0", name="price_usd_positive"),
        CheckConstraint(
            "platform_fee_usd + escrow_credit_usd = price_usd", name="purchase_split_matches_price"
        ),
        CheckConstraint("ends_at > starts_at", name="period_ordered"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    enrollment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("strategy_enrollments.id"), nullable=False
    )
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default=PaymentStatus.PENDING.value
    )
    price_usd: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    platform_fee_usd: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    escrow_credit_usd: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    razorpay_order_id: Mapped[str | None] = mapped_column(String(80))
    razorpay_payment_id: Mapped[str | None] = mapped_column(String(80), unique=True)
    idempotency_key: Mapped[str] = mapped_column(String(256), nullable=False)
    created_at: Mapped[datetime] = _created_at()
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PaymentOrder(Base):
    """Internal, idempotent Razorpay order record for purchases and top-ups."""

    __tablename__ = "payment_orders"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_payment_orders_idempotency_key"),
        UniqueConstraint("razorpay_order_id", name="uq_payment_orders_razorpay_order_id"),
        CheckConstraint(_in("purpose", PaymentPurpose), name="purpose_allowed"),
        CheckConstraint(_in("status", PaymentStatus), name="status_allowed"),
        CheckConstraint("amount_usd > 0", name="amount_usd_positive"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    enrollment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("strategy_enrollments.id"), nullable=False
    )
    purchase_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("strategy_purchases.id"))
    purpose: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default=PaymentStatus.PENDING.value
    )
    amount_usd: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    razorpay_order_id: Mapped[str | None] = mapped_column(String(80))
    razorpay_payment_id: Mapped[str | None] = mapped_column(String(80), unique=True)
    idempotency_key: Mapped[str] = mapped_column(String(256), nullable=False)
    created_at: Mapped[datetime] = _created_at()
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PaymentEvent(Base):
    """Raw-provider event metadata, deduplicated before fulfillment."""

    __tablename__ = "payment_events"
    __table_args__ = (
        UniqueConstraint("provider_event_id", name="uq_payment_events_provider_event_id"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    provider_event_id: Mapped[str] = mapped_column(String(160), nullable=False)
    event_type: Mapped[str] = mapped_column(String(96), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    received_at: Mapped[datetime] = _created_at()


class EscrowLedgerEntry(Base):
    """Append-only signed USD movements for one strategy enrollment."""

    __tablename__ = "escrow_ledger_entries"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_escrow_ledger_entries_idempotency_key"),
        CheckConstraint("amount <> 0", name="amount_non_zero"),
        CheckConstraint("currency = 'USD'", name="currency_usd"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    enrollment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("strategy_enrollments.id"), nullable=False
    )
    purchase_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("strategy_purchases.id"))
    settlement_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "strategy_settlements.id",
            use_alter=True,
            name="fk_escrow_ledger_entries_settlement_id_strategy_settlements",
        )
    )
    entry_type: Mapped[str] = mapped_column(String(32), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    idempotency_key: Mapped[str] = mapped_column(String(256), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(240))
    actor: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = _created_at()


class ClosedTradeAttribution(Base):
    """A managed closed broker deal eligible for exactly one settlement."""

    __tablename__ = "closed_trade_attributions"
    __table_args__ = (
        UniqueConstraint(
            "enrollment_id", "broker_deal_id", name="uq_closed_trade_attributions_enrollment_deal"
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    enrollment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("strategy_enrollments.id"), nullable=False
    )
    broker_deal_id: Mapped[str] = mapped_column(String(128), nullable=False)
    broker_position_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    closed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    net_realized_pnl: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    created_at: Mapped[datetime] = _created_at()


class StrategySettlement(Base):
    """Immutable daily closed-trade profit-share calculation."""

    __tablename__ = "strategy_settlements"
    __table_args__ = (
        UniqueConstraint(
            "enrollment_id", "period_start", name="uq_strategy_settlements_enrollment_period_start"
        ),
        UniqueConstraint("idempotency_key", name="uq_strategy_settlements_idempotency_key"),
        CheckConstraint("period_end > period_start", name="period_bounds_ordered"),
        CheckConstraint(
            "profit_share_rate >= 0 AND profit_share_rate <= 1",
            name="profit_share_rate_between_zero_and_one",
        ),
        CheckConstraint("profit_share_due >= 0", name="profit_share_due_non_negative"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    enrollment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("strategy_enrollments.id"), nullable=False
    )
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    net_closed_realized_pnl: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    profit_share_rate: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    profit_share_due: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(256), nullable=False)
    created_at: Mapped[datetime] = _created_at()


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
        # One entry or one managed operation per deterministic execution key.
        # A directional reversal may create several CLOSE intents (one for each
        # tracked opposite position) from the same BUY/SELL signal.
        UniqueConstraint(
            "user_id",
            "strategy_id",
            "signal_id",
            "command_target",
            "execution_key",
            name="uq_order_intents_signal_op_key",
        ),
        CheckConstraint("computed_lot > 0", name="computed_lot_positive"),
        CheckConstraint(_in("status", IntentStatus), name="status_allowed"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    strategy_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("strategies.id"), nullable=False)
    # Null only for legacy MVP intents created before marketplace enrollment.
    enrollment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("strategy_enrollments.id"))
    signal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("signals.id"), nullable=False)
    command_target: Mapped[str] = mapped_column(String(16), nullable=False)
    execution_key: Mapped[str] = mapped_column(String(128), nullable=False)

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
    account_ref: Mapped[str] = mapped_column(String(160), nullable=False, default="legacy")
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    volume: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = _created_at()


class Settlement(Base):
    """Immutable rent calculation for one user's closed-P&L period.

    ``net_closed_realized_pnl`` is supplied by the future execution
    attribution/settlement job. This table deliberately does not infer P&L
    from order or broker rows, which keeps manual trades out of the rent basis.
    """

    __tablename__ = "settlements"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "cadence",
            "period_start",
            name="uq_settlements_user_cadence_period_start",
        ),
        UniqueConstraint("idempotency_key", name="uq_settlements_idempotency_key"),
        CheckConstraint(_in("cadence", SettlementCadence), name="cadence_allowed"),
        CheckConstraint("period_end > period_start", name="period_bounds_ordered"),
        CheckConstraint(
            "rent_rate >= 0 AND rent_rate <= 1",
            name="rent_rate_between_zero_and_one",
        ),
        CheckConstraint("rent_due >= 0", name="rent_due_non_negative"),
        CheckConstraint("currency = 'USD'", name="currency_usd"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    cadence: Mapped[str] = mapped_column(
        String(8), nullable=False, default=SettlementCadence.DAILY.value
    )
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    net_closed_realized_pnl: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    rent_rate: Mapped[Decimal] = mapped_column(
        Numeric(9, 6), nullable=False, default=Decimal("0.10")
    )
    rent_due: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    idempotency_key: Mapped[str] = mapped_column(String(256), nullable=False)
    created_at: Mapped[datetime] = _created_at()

    user: Mapped[User] = relationship(back_populates="settlements")
    ledger_entries: Mapped[list[RentLedgerEntry]] = relationship(back_populates="settlement")


class RentLedgerEntry(Base):
    """One append-only signed movement in a user's USD rent wallet.

    Credits are positive and rent charges are negative. Corrections must be
    represented by a new ``ADJUSTMENT`` or ``REVERSAL`` row; existing entries
    must never be updated or deleted.
    """

    __tablename__ = "rent_ledger_entries"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_rent_ledger_entries_idempotency_key"),
        UniqueConstraint(
            "settlement_id",
            "entry_type",
            name="uq_rent_ledger_entries_settlement_entry_type",
        ),
        CheckConstraint(_in("entry_type", RentLedgerEntryType), name="entry_type_allowed"),
        CheckConstraint("amount <> 0", name="amount_non_zero"),
        CheckConstraint(
            "(entry_type <> 'RENT_CHARGE') OR (amount < 0)",
            name="rent_charge_negative",
        ),
        CheckConstraint(
            "(entry_type <> 'TOP_UP') OR (amount > 0)",
            name="top_up_positive",
        ),
        CheckConstraint(
            "(entry_type <> 'RENT_CHARGE') OR (settlement_id IS NOT NULL)",
            name="rent_charge_has_settlement",
        ),
        CheckConstraint("currency = 'USD'", name="currency_usd"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    settlement_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("settlements.id"))
    entry_type: Mapped[str] = mapped_column(String(16), nullable=False)
    # Signed amount in wallet currency: credits positive, charges negative.
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    idempotency_key: Mapped[str] = mapped_column(String(256), nullable=False)
    source_ref: Mapped[str | None] = mapped_column(String(128))
    reason: Mapped[str | None] = mapped_column(String(240))
    actor: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = _created_at()

    user: Mapped[User] = relationship(back_populates="rent_ledger_entries")
    settlement: Mapped[Settlement | None] = relationship(back_populates="ledger_entries")
