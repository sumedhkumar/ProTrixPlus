"""Signal ingestion: validate -> hash -> durably persist -> outbox, atomically.

Invariants enforced here (and traced by tests):

* **Durable before acknowledge** - the signal row and its outbox row are
  committed inside one transaction *before* this function returns. The endpoint
  only sends 2xx after that.
* **Idempotent acceptance** - a repeated ``signal_id`` (same body) returns the
  existing signal and creates nothing new. A repeated ``signal_id`` with a
  *different* body is a conflict.
* Malformed payloads raise before any write.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from protrix_contracts import (
    WebhookEnvelope,
    canonical_payload_hash,
    validate_envelope,
)
from protrix_contracts.db.models import Outbox, Signal
from protrix_contracts.money import quantize_fraction, quantize_money
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

log = logging.getLogger("api.ingest")

OUTBOX_AGGREGATE = "signal"
OUTBOX_EVENT_TYPE = "signal.accepted"


class SignalConflictError(Exception):
    """Same signal_id already stored with a different canonical payload."""


@dataclass(frozen=True)
class IngestResult:
    signal_row_id: str
    signal_id: str
    payload_hash: str
    duplicate: bool


def _idempotency_key(env: WebhookEnvelope) -> str:
    return f"{env.strategy_key}:{env.strategy_version}:{env.signal_id}"


def _parse_event_time(raw: str) -> datetime:
    dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    return dt.astimezone(UTC)


def _dec_or_none(value: str | None, quantizer: Any) -> Decimal | None:
    return None if value is None else quantizer(value)


def accept_signal(session: Session, payload: dict[str, Any]) -> IngestResult:
    # 1. Strict schema validation. Raises EnvelopeValidationError -> 422.
    validate_envelope(payload)
    env = WebhookEnvelope.from_validated(payload)

    # 2. Canonical hash + idempotency key.
    payload_hash = canonical_payload_hash(payload)
    idem = _idempotency_key(env)

    # 3. Fast path: already stored?
    existing = session.scalar(select(Signal).where(Signal.idempotency_key == idem))
    if existing is not None:
        return _resolve_existing(existing, payload_hash)

    # 4. Insert signal + outbox in one transaction.
    signal = Signal(
        signal_id=env.signal_id,
        idempotency_key=idem,
        payload_hash=payload_hash,
        schema_version=env.schema_version,
        strategy_key=env.strategy_key,
        strategy_version=env.strategy_version,
        action=env.action.value,
        symbol=env.symbol,
        timeframe=env.timeframe,
        position_ref=env.position_ref,
        close_fraction=_dec_or_none(env.close_fraction, quantize_fraction),
        stop_loss=_dec_or_none(env.stop_loss, quantize_money),
        take_profit=_dec_or_none(env.take_profit, quantize_money),
        raw_payload=payload,
        event_time_utc=_parse_event_time(env.event_time_utc),
        accepted_at=datetime.now(UTC),
    )
    session.add(signal)
    session.flush()  # populate signal.id

    session.add(
        Outbox(
            aggregate_type=OUTBOX_AGGREGATE,
            aggregate_id=signal.id,
            event_type=OUTBOX_EVENT_TYPE,
            payload={
                "signal_row_id": str(signal.id),
                "signal_id": env.signal_id,
                "strategy_key": env.strategy_key,
                "strategy_version": env.strategy_version,
                "payload_hash": payload_hash,
            },
        )
    )

    try:
        session.commit()
    except IntegrityError:
        # Concurrent insert of the same signal_id won the race. Fall back to the
        # stored row - still idempotent, still no duplicate.
        session.rollback()
        raced = session.scalar(select(Signal).where(Signal.idempotency_key == idem))
        if raced is None:
            raise
        log.info("signal insert raced; using stored row signal_id=%s", env.signal_id)
        return _resolve_existing(raced, payload_hash)

    log.info(
        "signal accepted signal_id=%s row_id=%s hash=%s",
        env.signal_id,
        signal.id,
        payload_hash,
    )
    return IngestResult(
        signal_row_id=str(signal.id),
        signal_id=env.signal_id,
        payload_hash=payload_hash,
        duplicate=False,
    )


def _resolve_existing(existing: Signal, payload_hash: str) -> IngestResult:
    if existing.payload_hash != payload_hash:
        raise SignalConflictError(
            f"signal_id {existing.signal_id!r} already stored with a different payload"
        )
    log.info("signal duplicate ignored signal_id=%s", existing.signal_id)
    return IngestResult(
        signal_row_id=str(existing.id),
        signal_id=existing.signal_id,
        payload_hash=existing.payload_hash,
        duplicate=True,
    )
