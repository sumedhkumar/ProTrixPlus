"""Idempotent seed of fake users + one strategy + assignments.

Deterministic UUIDs (uuid5) so re-running is a no-op and tests can predict ids.
Run as ``python -m app.seed``; the api entrypoint runs it after migrations.
"""

from __future__ import annotations

import logging
import uuid
from decimal import Decimal

from protrix_contracts.db.models import (
    Strategy,
    StrategyAssignment,
    User,
    UserRole,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.auth import hash_password
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

# Password-auth demo profiles surfaced by the login page's "1-Click Demo
# Profiles" buttons (web/app/login/page.tsx). All share DEMO_PASSWORD there.
DEMO_PASSWORD = "Demo12345!"
DEMO_PASSWORD_USERS = [
    ("demo-alex-vance", "SUPER_ADMIN", "Alex Vance", "alex.vance@protrixplus.test"),
    ("demo-marcus-sterling", "USER", "Marcus Sterling", "marcus.sterling@apexcapital.co"),
    ("demo-elena-rostova", "USER", "Elena Rostova", "elena.rostova@quantfund.net"),
]


def user_id(slug: str) -> uuid.UUID:
    return uuid.uuid5(_NS, f"user:{slug}")


def strategy_id() -> uuid.UUID:
    return uuid.uuid5(_NS, f"strategy:{STRATEGY_KEY}:{STRATEGY_VERSION}")


def assignment_id(slug: str) -> uuid.UUID:
    return uuid.uuid5(_NS, f"assignment:{slug}")


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

        demo_password_hash = hash_password(DEMO_PASSWORD)
        for slug, role, name, email in DEMO_PASSWORD_USERS:
            session.execute(
                pg_insert(User)
                .values(
                    id=user_id(slug),
                    email=email,
                    display_name=name,
                    role=UserRole(role).value,
                    is_active=True,
                    password_hash=demo_password_hash,
                )
                .on_conflict_do_nothing(index_elements=["id"])
            )

        for slug, role, _name, _email in FAKE_USERS:
            if role != "USER":
                continue
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
