"""Idempotent seed of fake users + one strategy + assignments.

Deterministic UUIDs (uuid5) so re-running is a no-op and tests can predict ids.
Run as ``python -m app.seed``; the api entrypoint runs it after migrations.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from protrix_contracts.db.models import (
    AccountCategory,
    AccountTransport,
    RentLedgerEntry,
    RentLedgerEntryType,
    RiskProfile,
    Strategy,
    StrategyAssignment,
    StrategyOffer,
    Subscription,
    SubscriptionStatus,
    TradingAccount,
    TradingAccountStatus,
    TradingControl,
    User,
    UserRole,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db import get_session_factory

log = logging.getLogger("api.seed")

_NS = uuid.UUID("2f5b7c9a-0000-4000-8000-a1b2c3d4e5f6")

STRATEGY_KEY = "trend-rider"
STRATEGY_VERSION = "2025.09"

FAKE_USERS = [
    ("alice", "USER", "Alice Trader", "alice@example.test"),
    ("bob", "USER", "Bob Trader", "bob@example.test"),
    ("carol", "USER", "Carol Trader", "carol@example.test"),
    ("root", "SUPER_ADMIN", "Root Admin", "root@example.test"),
]


def user_id(slug: str) -> uuid.UUID:
    return uuid.uuid5(_NS, f"user:{slug}")


def strategy_id() -> uuid.UUID:
    return uuid.uuid5(_NS, f"strategy:{STRATEGY_KEY}:{STRATEGY_VERSION}")


def assignment_id(slug: str) -> uuid.UUID:
    return uuid.uuid5(_NS, f"assignment:{slug}")


def offer_id() -> uuid.UUID:
    return uuid.uuid5(_NS, f"offer:{STRATEGY_KEY}:{STRATEGY_VERSION}")


def seed() -> None:
    factory = get_session_factory()
    with factory() as session:
        session.execute(
            pg_insert(Strategy)
            .values(
                id=strategy_id(),
                strategy_key=STRATEGY_KEY,
                strategy_version=STRATEGY_VERSION,
                name="Trend Rider (skeleton)",
                is_active=True,
            )
            .on_conflict_do_nothing(index_elements=["id"])
        )
        session.execute(
            pg_insert(StrategyOffer)
            .values(
                id=offer_id(),
                strategy_id=strategy_id(),
                description=(
                    "A managed trend-following route with isolated MT5 execution and escrow."
                ),
                price_usd=Decimal("100.00"),
                platform_fee_usd=Decimal("20.00"),
                escrow_credit_usd=Decimal("80.00"),
                duration_days=30,
                minimum_wallet_usd=Decimal("10.00"),
                profit_share_rate=Decimal("0.10"),
                is_published=True,
            )
            .on_conflict_do_nothing(index_elements=["strategy_id"])
        )

        for slug, role, name, email in FAKE_USERS:
            session.execute(
                pg_insert(User)
                .values(
                    id=user_id(slug),
                    email=email,
                    display_name=name,
                    role=UserRole(role).value,
                    is_active=True,
                )
                .on_conflict_do_nothing(index_elements=["id"])
            )

        for slug, role, _name, _email in FAKE_USERS:
            if role != "USER":
                continue
            now = datetime.now(UTC)
            session.execute(
                pg_insert(TradingAccount)
                .values(
                    id=user_id(slug),
                    user_id=user_id(slug),
                    provider_name="Local development",
                    server_identifier="MOCK_SERVER",
                    category=AccountCategory.DEMO.value,
                    transport=AccountTransport.MOCK.value,
                    status=TradingAccountStatus.ACTIVE.value,
                    credential_key_ref=f"local-profile:{slug}",
                )
                .on_conflict_do_nothing(index_elements=["id"])
            )
            session.execute(
                pg_insert(Subscription)
                .values(
                    id=uuid.uuid5(_NS, f"subscription:{slug}"),
                    user_id=user_id(slug),
                    plan_code="MVP_DEMO",
                    status=SubscriptionStatus.ACTIVE.value,
                    starts_at=now,
                    ends_at=now + timedelta(days=365),
                )
                .on_conflict_do_nothing(index_elements=["user_id"])
            )
            session.execute(
                pg_insert(TradingControl)
                .values(id=uuid.uuid5(_NS, f"control:{slug}"), user_id=user_id(slug))
                .on_conflict_do_nothing(index_elements=["user_id"])
            )
            session.execute(
                pg_insert(RiskProfile)
                .values(
                    id=uuid.uuid5(_NS, f"risk:{slug}"),
                    user_id=user_id(slug),
                    max_lot=Decimal("2.00"),
                    max_open_trades=10,
                    max_daily_loss=Decimal("1000.00"),
                    allowed_symbols=["XAUUSD", "EURUSD"],
                )
                .on_conflict_do_nothing(index_elements=["user_id"])
            )
            session.execute(
                pg_insert(RentLedgerEntry)
                .values(
                    id=uuid.uuid5(_NS, f"demo-credit:{slug}"),
                    user_id=user_id(slug),
                    entry_type=RentLedgerEntryType.TOP_UP.value,
                    amount=Decimal("1000.00"),
                    idempotency_key=f"seed:demo-credit:{slug}",
                    source_ref="MVP_DEMO",
                    reason="local demo starting wallet balance",
                    actor="seed",
                )
                .on_conflict_do_nothing(index_elements=["idempotency_key"])
            )
            session.execute(
                pg_insert(StrategyAssignment)
                .values(
                    id=assignment_id(slug),
                    user_id=user_id(slug),
                    strategy_id=strategy_id(),
                    master_lot=Decimal("1.00"),
                    multiplier=Decimal("1.0000"),
                    multiplier_min=Decimal("0.5000"),
                    multiplier_max=Decimal("2.0000"),
                    status="ACTIVE",
                )
                .on_conflict_do_nothing(index_elements=["id"])
            )
        session.commit()
    log.info("seed complete: %d users, 1 strategy", len(FAKE_USERS))


if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level="INFO")
    seed()
