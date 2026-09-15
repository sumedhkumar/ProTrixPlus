"""Shared SQLAlchemy models + session helpers.

PostgreSQL is the source of truth. The uniqueness and check constraints that
protect the invariants live in :mod:`protrix_contracts.db.models` and are created
by Alembic - not merely asserted in application code.
"""

from protrix_contracts.db.base import Base, metadata
from protrix_contracts.db.models import (
    AccountCategory,
    AccountTransport,
    AuditEvent,
    Execution,
    MockBrokerDeal,
    OrderIntent,
    Outbox,
    OutboxStatus,
    RentLedgerEntry,
    RentLedgerEntryType,
    RiskProfile,
    Settlement,
    SettlementCadence,
    Signal,
    Strategy,
    StrategyAssignment,
    Subscription,
    SubscriptionStatus,
    TradingControl,
    TradingAccount,
    TradingAccountStatus,
    ManagedPosition,
    ManagedPositionStatus,
    User,
    UserRole,
)
from protrix_contracts.db.session import (
    build_engine,
    build_session_factory,
    session_scope,
)

__all__ = [
    "Base",
    "metadata",
    "User",
    "UserRole",
    "TradingAccount",
    "TradingAccountStatus",
    "AccountCategory",
    "AccountTransport",
    "Subscription",
    "SubscriptionStatus",
    "TradingControl",
    "RiskProfile",
    "ManagedPosition",
    "ManagedPositionStatus",
    "Strategy",
    "StrategyAssignment",
    "Signal",
    "Outbox",
    "OutboxStatus",
    "OrderIntent",
    "Execution",
    "AuditEvent",
    "MockBrokerDeal",
    "Settlement",
    "SettlementCadence",
    "RentLedgerEntry",
    "RentLedgerEntryType",
    "build_engine",
    "build_session_factory",
    "session_scope",
]
