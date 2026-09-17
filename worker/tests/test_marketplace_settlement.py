from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from protrix_contracts.db.models import (
    ClosedTradeAttribution,
    EscrowLedgerEntry,
    Strategy,
    StrategyEnrollment,
    StrategySettlement,
    User,
)
from sqlalchemy import func, select

from app.settlement import settle_utc_day


@pytest.mark.dbtest
def test_daily_closed_pnl_charge_can_make_escrow_negative(sf, clean_db) -> None:
    day = datetime(2026, 9, 15, tzinfo=UTC)
    with sf() as session:
        user = User(email="wallet@example.test", display_name="Wallet", role="USER")
        strategy = Strategy(
            strategy_key="wallet-test", strategy_version="1", name="Wallet test", is_active=True
        )
        session.add_all([user, strategy])
        session.flush()
        enrollment = StrategyEnrollment(
            user_id=user.id,
            strategy_id=strategy.id,
            status="ACTIVE",
            minimum_wallet_usd=Decimal("10.00"),
            profit_share_rate=Decimal("0.10"),
        )
        session.add(enrollment)
        session.flush()
        session.add(
            EscrowLedgerEntry(
                enrollment_id=enrollment.id,
                entry_type="PURCHASE_ESCROW_CREDIT",
                amount=Decimal("11.00"),
                idempotency_key="initial-credit",
                reason="test",
                actor="test",
            )
        )
        session.add(
            ClosedTradeAttribution(
                enrollment_id=enrollment.id,
                broker_deal_id="deal-1",
                broker_position_ref="position-1",
                closed_at=day.replace(hour=12),
                net_realized_pnl=Decimal("120.00"),
            )
        )
        session.commit()

    assert settle_utc_day(sf, period_start=day) == 1
    assert settle_utc_day(sf, period_start=day) == 0

    with sf() as session:
        settlement = session.scalar(select(StrategySettlement))
        assert settlement is not None
        assert settlement.profit_share_due == Decimal("12.00000000")
        balance = session.scalar(select(func.sum(EscrowLedgerEntry.amount)))
        assert balance == Decimal("-1.00000000")
