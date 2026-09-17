"""Startup catch-up sweep.

Runs fan-out again for recent signals so that anything persisted by api while
the worker was down (or a message lost from Redis) is still picked up. Fan-out
is idempotent, so this can never duplicate an intent or execution.
"""

from __future__ import annotations

import logging
import uuid

from protrix_contracts.db.models import Signal
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.base import ExecutionAdapter
from app.fanout import process_signal

log = logging.getLogger("worker.catch_up")


def run_catch_up(
    session_factory: sessionmaker[Session],
    adapter: ExecutionAdapter,
    *,
    limit: int = 500,
    active_user_email: str | None = None,
    active_enrollment_id: uuid.UUID | None = None,
    active_transport: str | None = None,
) -> int:
    with session_factory() as session:
        signal_ids = list(
            session.scalars(select(Signal.id).order_by(Signal.created_at.desc()).limit(limit)).all()
        )

    for signal_id in signal_ids:
        session = session_factory()
        try:
            process_signal(
                session,
                signal_id,
                adapter,
                active_user_email=active_user_email,
                active_enrollment_id=active_enrollment_id,
                active_transport=active_transport,
            )
        except Exception:
            log.exception("catch-up: failed on signal %s", signal_id)
        finally:
            session.close()

    log.info("catch-up sweep complete over %d signal(s)", len(signal_ids))
    return len(signal_ids)
