"""Outbox relay: PENDING rows move to the Redis stream and are marked PUBLISHED,
and the row stays in the table (Redis is never the only record)."""

from __future__ import annotations

import uuid

import pytest
from protrix_contracts.db.models import Outbox
from sqlalchemy import select

from app.relay import relay_once

pytestmark = pytest.mark.dbtest

STREAM = "test.signals"


def test_relay_moves_pending_to_stream_and_marks_published(sf, redis_client, clean_db) -> None:
    agg_id = uuid.uuid4()
    with sf() as session:
        session.add(
            Outbox(
                aggregate_type="signal",
                aggregate_id=agg_id,
                event_type="signal.accepted",
                payload={"signal_id": "sig-relay-1", "signal_row_id": str(agg_id)},
            )
        )
        session.commit()

    moved = relay_once(sf, redis_client, stream=STREAM, batch=10)
    assert moved == 1

    entries = redis_client.xrange(STREAM)
    assert len(entries) == 1
    _id, fields = entries[0]
    assert fields["aggregate_id"] == str(agg_id)
    assert fields["event_type"] == "signal.accepted"

    with sf() as session:
        row = session.scalar(select(Outbox).where(Outbox.aggregate_id == agg_id))
        assert row is not None  # still there
        assert row.status == "PUBLISHED"
        assert row.published_at is not None

    # Second pass moves nothing.
    assert relay_once(sf, redis_client, stream=STREAM, batch=10) == 0
