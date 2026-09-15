"""Redis Streams consumer group -> signal fan-out.

Restart safety: on every tick the consumer first ``XAUTOCLAIM``s messages that
were delivered to a now-dead consumer and never ACK'd, then reads new ones. Fan
-out is idempotent, so re-processing a reclaimed message creates no duplicates.
A message is only ``XACK``'d after its fan-out commits.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, cast

from redis import Redis
from redis.exceptions import ResponseError
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.base import ExecutionAdapter
from app.fanout import process_signal

StreamEntry = tuple[str, dict[str, str]]

log = logging.getLogger("worker.consumer")


def ensure_group(redis: Redis, stream: str, group: str, *, start_id: str = "$") -> None:
    """Create a consumer group without replaying older stream entries.

    Startup recovery is handled separately by the database catch-up sweep when
    enabled. Starting a newly provisioned account route at ``$`` prevents a
    second MT5 worker from replaying historical TradingView alerts and placing
    unintended orders.
    """

    try:
        redis.xgroup_create(name=stream, groupname=group, id=start_id, mkstream=True)
        log.info("created consumer group %s on %s", group, stream)
    except ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


def _is_nogroup(exc: BaseException) -> bool:
    return "NOGROUP" in str(exc)


def _handle(
    session_factory: sessionmaker[Session],
    fields: dict[str, str],
    adapter: ExecutionAdapter,
    active_user_email: str | None,
) -> None:
    aggregate_id = fields.get("aggregate_id")
    aggregate_type = fields.get("aggregate_type", "signal")
    if aggregate_type != "signal" or not aggregate_id:
        log.warning("ignoring stream entry: %s", fields)
        return
    session = session_factory()
    try:
        process_signal(
            session,
            uuid.UUID(aggregate_id),
            adapter,
            active_user_email=active_user_email,
        )
    finally:
        session.close()


def consume_once(
    session_factory: sessionmaker[Session],
    redis: Redis,
    adapter: ExecutionAdapter,
    *,
    stream: str,
    group: str,
    consumer: str,
    reclaim_idle_ms: int,
    active_user_email: str | None = None,
    block_ms: int = 2000,
    count: int = 10,
) -> int:
    entries: list[StreamEntry] = []

    try:
        autoclaim = cast(
            "tuple[Any, list[StreamEntry], Any]",
            redis.xautoclaim(
                name=stream,
                groupname=group,
                consumername=consumer,
                min_idle_time=reclaim_idle_ms,
                count=count,
            ),
        )
        entries.extend(autoclaim[1])
    except ResponseError as exc:
        # The stream/group can vanish under us (redis restart with no
        # persistence, FLUSHDB, failover). Recreate and carry on rather than
        # erroring forever.
        if _is_nogroup(exc):
            log.warning("consumer group gone; recreating %s/%s", stream, group)
            ensure_group(redis, stream, group)
        else:  # pragma: no cover - defensive
            log.warning("xautoclaim failed: %s", exc)

    try:
        resp = cast(
            "list[tuple[str, list[StreamEntry]]]",
            redis.xreadgroup(
                groupname=group,
                consumername=consumer,
                streams={stream: ">"},
                count=count,
                block=block_ms,
            )
            or [],
        )
    except ResponseError as exc:
        if _is_nogroup(exc):
            log.warning("consumer group gone; recreating %s/%s", stream, group)
            ensure_group(redis, stream, group)
            resp = []
        else:
            raise
    for _stream_name, msgs in resp:
        entries.extend(msgs)

    processed = 0
    for msg_id, fields in entries:
        try:
            _handle(session_factory, fields, adapter, active_user_email)
            redis.xack(stream, group, msg_id)
            processed += 1
        except Exception:
            log.exception("failed to process stream entry %s; left un-acked", msg_id)
    return processed
