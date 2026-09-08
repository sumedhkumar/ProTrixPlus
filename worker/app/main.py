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

from redis import Redis
from sqlalchemy import text

from app.adapter_factory import build_adapter
from app.catch_up import run_catch_up
from app.config import WorkerConfig
from app.consumer import consume_once, ensure_group
from app.db import engine, init_db, session_factory
from app.health import start_health_server
from app.logging_config import configure_logging
from app.relay import relay_once

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


def _consumer_loop(cfg: WorkerConfig, redis: Redis, adapter: object, stop: threading.Event) -> None:
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
            )
        except Exception:
            log.exception("consumer loop error")
            stop.wait(1.0)


def main() -> int:
    cfg = WorkerConfig.from_env()
    configure_logging(level=cfg.log_level, service=cfg.service_name)
    log.info("worker starting name=%s adapter=%s", cfg.consumer_name, cfg.execution_adapter)

    init_db(cfg.database_url)
    redis: Redis = Redis.from_url(cfg.redis_url, decode_responses=True)
    _wait_for_deps(redis)

    ensure_group(redis, cfg.signal_stream, cfg.consumer_group)
    adapter = build_adapter(cfg.execution_adapter, session_factory(), redis)

    start_health_server(
        port=cfg.health_port,
        engine=engine(),
        redis_url=cfg.redis_url,
        service=cfg.service_name,
    )

    if cfg.catch_up_on_start:
        try:
            run_catch_up(session_factory(), adapter)
        except Exception:
            log.exception("startup catch-up failed (continuing)")

    stop = threading.Event()

    def _graceful(signum: int, _frame: object) -> None:
        log.info("signal %s received; stopping", signum)
        stop.set()

    signal.signal(signal.SIGINT, _graceful)
    signal.signal(signal.SIGTERM, _graceful)

    threads = [
        threading.Thread(target=_relay_loop, args=(cfg, redis, stop), name="relay"),
        threading.Thread(target=_consumer_loop, args=(cfg, redis, adapter, stop), name="consumer"),
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
