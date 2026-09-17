"""Persist native worker liveness for dashboard operations views."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from protrix_contracts.db.models import EnrollmentAccount, TradingAccount, User
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.config import WorkerConfig


def record_heartbeat(session_factory: sessionmaker[Session], cfg: WorkerConfig) -> bool:
    """Record liveness for one explicit native account route.

    Mock workers intentionally do not claim a customer account heartbeat.
    """
    if cfg.execution_adapter != "mt5":
        return False
    with session_factory() as session:
        enrollment_id = getattr(cfg, "mt5_enrollment_id", "")
        account: EnrollmentAccount | TradingAccount | None = None
        if enrollment_id:
            try:
                account = session.scalar(
                    select(EnrollmentAccount).where(
                        EnrollmentAccount.enrollment_id == UUID(enrollment_id)
                    )
                )
            except ValueError:
                return False
        else:
            account = session.scalar(
                select(TradingAccount)
                .join(User, TradingAccount.user_id == User.id)
                .where(User.email == cfg.mt5_user_email)
            )
        if account is None:
            return False
        account.worker_adapter = cfg.execution_adapter
        account.worker_name = cfg.consumer_name
        account.worker_heartbeat_at = datetime.now(UTC)
        session.commit()
    return True
