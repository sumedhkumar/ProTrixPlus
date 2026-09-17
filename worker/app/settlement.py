"""Idempotent UTC-day profit-share settlement for marketplace enrollments."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from protrix_contracts.db.models import (
    ClosedTradeAttribution,
    EscrowLedgerEntry,
    StrategyEnrollment,
    StrategySettlement,
)
from protrix_contracts.rent import calculate_rent_due, signed_rent_charge
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.base import ExecutionAdapter

log = logging.getLogger("worker.settlement")


def previous_utc_day(now: datetime | None = None) -> datetime:
    value = (now or datetime.now(UTC)).astimezone(UTC)
    return value.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)


def attribute_closed_deals(
    session_factory: sessionmaker[Session],
    adapter: ExecutionAdapter,
    *,
    enrollment_id: uuid.UUID,
    account_ref: str,
) -> int:
    """Persist broker exits as immutable, per-enrollment PnL attribution.

    The one-day overlap protects against delayed broker history.  The database
    uniqueness key makes the overlap and worker restarts safe to replay.
    """
    with session_factory() as session:
        latest = session.scalar(
            select(func.max(ClosedTradeAttribution.closed_at)).where(
                ClosedTradeAttribution.enrollment_id == enrollment_id
            )
        )
    since = (latest - timedelta(days=1)) if latest else previous_utc_day() - timedelta(days=1)
    deals = adapter.sync_closed_deals(account_ref, since)
    written = 0
    with session_factory() as session:
        for deal in deals:
            exists = session.scalar(
                select(ClosedTradeAttribution.id).where(
                    ClosedTradeAttribution.enrollment_id == enrollment_id,
                    ClosedTradeAttribution.broker_deal_id == deal.deal_id,
                )
            )
            if exists is not None:
                continue
            session.add(
                ClosedTradeAttribution(
                    enrollment_id=enrollment_id,
                    broker_deal_id=deal.deal_id,
                    broker_position_ref=deal.position_ref,
                    closed_at=deal.closed_at,
                    net_realized_pnl=deal.net_realized_pnl,
                )
            )
            written += 1
        session.commit()
    return written


def settle_utc_day(
    session_factory: sessionmaker[Session], *, period_start: datetime | None = None
) -> int:
    """Write one immutable settlement per enrollment for a completed UTC day.

    A charge is intentionally posted in full even when it takes escrow below
    zero. The eligibility gate pauses future entries below the per-strategy
    minimum; a later top-up offsets the negative ledger balance naturally.
    """
    start = (period_start or previous_utc_day()).astimezone(UTC)
    start = start.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    with session_factory() as session:
        enrollment_ids = list(session.scalars(select(StrategyEnrollment.id)))

    written = 0
    for enrollment_id in enrollment_ids:
        try:
            with session_factory() as session:
                existing = session.scalar(
                    select(StrategySettlement.id).where(
                        StrategySettlement.enrollment_id == enrollment_id,
                        StrategySettlement.period_start == start,
                    )
                )
                if existing is not None:
                    continue
                enrollment = session.get(StrategyEnrollment, enrollment_id)
                if enrollment is None:
                    continue
                pnl = session.scalar(
                    select(
                        func.coalesce(
                            func.sum(ClosedTradeAttribution.net_realized_pnl), Decimal("0")
                        )
                    ).where(
                        ClosedTradeAttribution.enrollment_id == enrollment_id,
                        ClosedTradeAttribution.closed_at >= start,
                        ClosedTradeAttribution.closed_at < end,
                    )
                )
                net_pnl = Decimal(pnl if pnl is not None else Decimal("0"))
                due = calculate_rent_due(net_pnl, enrollment.profit_share_rate)
                settlement = StrategySettlement(
                    enrollment_id=enrollment_id,
                    period_start=start,
                    period_end=end,
                    net_closed_realized_pnl=net_pnl,
                    profit_share_rate=enrollment.profit_share_rate,
                    profit_share_due=due,
                    idempotency_key=f"daily-profit-share:{enrollment_id}:{start.date().isoformat()}",
                )
                session.add(settlement)
                session.flush()
                if due > 0:
                    session.add(
                        EscrowLedgerEntry(
                            enrollment_id=enrollment_id,
                            settlement_id=settlement.id,
                            entry_type="RENT_CHARGE",
                            amount=signed_rent_charge(due),
                            idempotency_key=f"profit-share-charge:{settlement.id}",
                            reason=f"10% closed-trade profit share for {start.date().isoformat()}",
                            actor="settlement-worker",
                        )
                    )
                session.commit()
                written += 1
        except IntegrityError:
            # The unique enrollment/day key makes a concurrent scheduler a safe
            # replay rather than a second financial charge.
            log.info("settlement replay ignored enrollment=%s day=%s", enrollment_id, start.date())
    if written:
        log.info("settled %d enrollment(s) for UTC day %s", written, start.date())
    return written
