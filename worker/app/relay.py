"""Transactional-outbox relay: PostgreSQL ``outbox`` -> Redis stream.

Redis is never the only record. A row is XADD'd to the stream and then marked
PUBLISHED in the same DB transaction; the row stays in ``outbox`` as durable
proof. ``SELECT ... FOR UPDATE SKIP LOCKED`` lets multiple relay loops run
without double-publishing.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from protrix_contracts.db.models import Outbox, OutboxStatus
from redis import Redis
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

log = logging.getLogger("worker.relay")


def relay_once(
    session_factory: sessionmaker[Session], redis: Redis, *, stream: str, batch: int
) -> int:
    session = session_factory()
    try:
        rows = (
            session.execute(
                select(Outbox)
                .where(
                    Outbox.status == OutboxStatus.PENDING.value,
                    Outbox.available_at <= datetime.now(UTC),
                )
                .order_by(Outbox.created_at)
                .limit(batch)
                .with_for_update(skip_locked=True)
            )
            .scalars()
            .all()
        )
        for row in rows:
            redis.xadd(
                stream,
                {
                    "outbox_id": str(row.id),
                    "event_type": row.event_type,
                    "aggregate_type": row.aggregate_type,
                    "aggregate_id": str(row.aggregate_id),
                    "payload": json.dumps(row.payload),
                },
            )
            row.status = OutboxStatus.PUBLISHED.value
            row.published_at = datetime.now(UTC)
            row.attempts += 1
        session.commit()
        if rows:
            log.info("relayed %d outbox row(s) to %s", len(rows), stream)
        return len(rows)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
