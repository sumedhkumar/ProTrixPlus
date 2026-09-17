"""Worker entrypoint.

Three cooperating loops on daemon threads:

1. health HTTP server (:8000/health)
2. outbox relay   (PostgreSQL outbox -> Redis stream)
3. signal consumer (Redis stream -> idempotent fan-out -> mock execution)

Plus a one-shot catch-up sweep on startup. SIGINT/SIGTERM flip a stop event and
every loop drains and exits.
"""

from __future__ import annotations

import logging
import signal
import sys
import threading
import time
import uuid
from typing import cast

from protrix_contracts.db.models import AccountTransport
from redis import Redis
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.adapter_factory import build_adapter
from app.catch_up import run_catch_up
from app.config import WorkerConfig
from app.consumer import consume_once, ensure_group
from app.db import engine, init_db, session_factory
from app.health import start_health_server
from app.heartbeat import record_heartbeat
from app.logging_config import configure_logging
from app.reconciliation import reconcile_pending_entries
from app.relay import relay_once
from app.settlement import attribute_closed_deals, settle_utc_day

log = logging.getLogger("worker")


def _wait_for_deps(redis: Redis, *, attempts: int = 60) -> None:
    for i in range(attempts):
        try:
            with engine().connect() as conn:
                conn.execute(text("SELECT 1"))
            redis.ping()
            log.info("dependencies ready")
            return
        except Exception as exc:  # noqa: BLE001
            log.info("waiting for deps (%d): %s", i, exc.__class__.__name__)
            time.sleep(1)
    raise SystemExit("dependencies never became ready")


def _relay_loop(cfg: WorkerConfig, redis: Redis, stop: threading.Event) -> None:
    while not stop.is_set():
        try:
            moved = relay_once(
                session_factory(), redis, stream=cfg.signal_stream, batch=cfg.relay_batch
            )
        except Exception:
            log.exception("relay loop error")
            moved = 0
        stop.wait(0.05 if moved else cfg.relay_poll_seconds)


def _enrollment_route(cfg: WorkerConfig) -> uuid.UUID | None:
    if not cfg.mt5_enrollment_id:
        return None
    if cfg.execution_adapter != "mt5":
        raise SystemExit("PROTRIX_MT5_ENROLLMENT_ID requires PROTRIX_EXECUTION_ADAPTER=mt5")
    try:
        return uuid.UUID(cfg.mt5_enrollment_id)
    except ValueError as exc:
        raise SystemExit("PROTRIX_MT5_ENROLLMENT_ID must be a UUID") from exc


def _consumer_loop(
    cfg: WorkerConfig,
    redis: Redis,
    adapter: object,
    stop: threading.Event,
    enrollment_id: uuid.UUID | None,
    active_transport: str,
) -> None:
    while not stop.is_set():
        try:
            consume_once(
                session_factory(),
                redis,
                adapter,  # type: ignore[arg-type]
                stream=cfg.signal_stream,
                group=cfg.consumer_group,
                consumer=cfg.consumer_name,
                reclaim_idle_ms=cfg.reclaim_idle_ms,
                active_user_email=cfg.mt5_user_email
                if cfg.execution_adapter == "mt5" and enrollment_id is None
                else None,
                active_enrollment_id=enrollment_id,
                active_transport=active_transport,
            )
        except Exception:
            log.exception("consumer loop error")
            stop.wait(1.0)


def _operations_loop(
    cfg: WorkerConfig,
    adapter: object,
    stop: threading.Event,
    enrollment_id: uuid.UUID | None,
    active_transport: str,
) -> None:
    """Keep account liveness current and reconcile only safe UNKNOWN entries."""
    next_heartbeat = 0.0
    next_reconciliation = 0.0
    next_settlement = 0.0
    next_attribution = 0.0
    while not stop.is_set():
        now = time.monotonic()
        if now >= next_heartbeat:
            try:
                record_heartbeat(session_factory(), cfg)
            except Exception:  # noqa: BLE001
                log.exception("worker heartbeat update failed")
            next_heartbeat = now + cfg.heartbeat_interval_seconds
        if now >= next_reconciliation:
            try:
                reconcile_pending_entries(
                    session_factory(),
                    adapter,  # type: ignore[arg-type]
                    active_user_email=cfg.mt5_user_email
                    if cfg.execution_adapter == "mt5" and enrollment_id is None
                    else None,
                    active_enrollment_id=enrollment_id,
                    active_transport=active_transport,
                )
            except Exception:  # noqa: BLE001
                log.exception("background reconciliation failed")
            next_reconciliation = now + cfg.reconcile_interval_seconds
        if enrollment_id is not None and now >= next_attribution:
            try:
                from protrix_contracts.db.models import EnrollmentAccount

                session = cast(Session, session_factory()())
                try:
                    account = session.scalar(
                        select(EnrollmentAccount).where(
                            EnrollmentAccount.enrollment_id == enrollment_id
                        )
                    )
                    account_ref = (
                        (account.external_account_ref or f"enrollment-{enrollment_id}")
                        if account is not None
                        else None
                    )
                finally:
                    session.close()
                if account_ref is not None:
                    attribute_closed_deals(
                        session_factory(),
                        adapter,  # type: ignore[arg-type]
                        enrollment_id=enrollment_id,
                        account_ref=account_ref,
                    )
            except Exception:  # noqa: BLE001
                log.exception("closed-trade attribution failed")
            next_attribution = now + cfg.reconcile_interval_seconds
        if now >= next_settlement:
            try:
                # The writer's unique enrollment/day key makes periodic retry
                # safe and ensures restarts do not double-charge users.
                settle_utc_day(session_factory())
            except Exception:  # noqa: BLE001
                log.exception("daily settlement failed")
            next_settlement = now + 3600
        stop.wait(0.5)


def main() -> int:
    cfg = WorkerConfig.from_env()
    enrollment_id = _enrollment_route(cfg)
    active_transport = (
        AccountTransport.NATIVE_MT5.value
        if cfg.execution_adapter == "mt5"
        else AccountTransport.MOCK.value
    )
    configure_logging(level=cfg.log_level, service=cfg.service_name, secrets=[cfg.mt5_password])
    log.info(
        "worker starting name=%s adapter=%s route_user=%s signal_group=%s",
        cfg.consumer_name,
        cfg.execution_adapter,
        cfg.mt5_enrollment_id or cfg.mt5_user_email
        if cfg.execution_adapter == "mt5"
        else "all-users",
        cfg.consumer_group,
    )

    init_db(cfg.database_url)
    redis: Redis = Redis.from_url(cfg.redis_url, decode_responses=True)
    _wait_for_deps(redis)

    ensure_group(redis, cfg.signal_stream, cfg.consumer_group)
    adapter = build_adapter(cfg.execution_adapter, session_factory(), redis, cfg)

    start_health_server(
        port=cfg.health_port,
        engine=engine(),
        redis_url=cfg.redis_url,
        service=cfg.service_name,
    )

    if cfg.catch_up_on_start:
        try:
            run_catch_up(
                session_factory(),
                adapter,
                active_user_email=cfg.mt5_user_email
                if cfg.execution_adapter == "mt5" and enrollment_id is None
                else None,
                active_enrollment_id=enrollment_id,
                active_transport=active_transport,
            )
        except Exception:
            log.exception("startup catch-up failed (continuing)")

    try:
        record_heartbeat(session_factory(), cfg)
    except Exception:  # noqa: BLE001
        log.exception("initial worker heartbeat update failed")

    stop = threading.Event()

    def _graceful(signum: int, _frame: object) -> None:
        log.info("signal %s received; stopping", signum)
        stop.set()

    signal.signal(signal.SIGINT, _graceful)
    signal.signal(signal.SIGTERM, _graceful)

    threads = [
        threading.Thread(target=_relay_loop, args=(cfg, redis, stop), name="relay"),
        threading.Thread(
            target=_consumer_loop,
            args=(cfg, redis, adapter, stop, enrollment_id, active_transport),
            name="consumer",
        ),
        threading.Thread(
            target=_operations_loop,
            args=(cfg, adapter, stop, enrollment_id, active_transport),
            name="operations",
        ),
    ]
    for t in threads:
        t.start()
    try:
        while not stop.is_set():
            time.sleep(0.5)
    finally:
        stop.set()
        for t in threads:
            t.join(timeout=10)
    log.info("worker stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
