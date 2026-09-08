"""Integration-ish: signal ingestion invariants against a real PostgreSQL."""

from __future__ import annotations

import copy

import pytest
from protrix_contracts.db.models import Outbox, Signal
from sqlalchemy import func, select

from app.services.ingest import SignalConflictError, accept_signal

pytestmark = pytest.mark.dbtest

VALID: dict = {
    "schema_version": "1.0",
    "strategy_key": "trend-rider",
    "strategy_version": "2025.09",
    "signal_id": "sig-db-1",
    "event_time_utc": "2026-09-08T10:15:00Z",
    "action": "BUY",
    "symbol": "EURUSD",
    "timeframe": "15m",
    "master_lot_info": {"master_lot": "3.00", "note": "informational only"},
}


def test_signal_and_outbox_written_in_one_unit(db) -> None:
    """accept_signal persists the signal AND its outbox row before it returns.
    (The cross-process 'durable before HTTP 2xx' proof lives in
    tests/test_slice_end_to_end.py, which reads back over a fresh connection.)"""
    result = accept_signal(db, copy.deepcopy(VALID))
    assert result.duplicate is False

    sig = db.scalar(select(Signal).where(Signal.signal_id == "sig-db-1"))
    assert sig is not None and sig.accepted_at is not None
    obx = db.scalar(select(Outbox).where(Outbox.aggregate_id == sig.id))
    assert obx is not None
    assert obx.event_type == "signal.accepted"
    assert obx.status == "PENDING"


def test_repeated_signal_id_is_idempotent(db) -> None:
    first = accept_signal(db, copy.deepcopy(VALID))
    second = accept_signal(db, copy.deepcopy(VALID))
    assert second.duplicate is True
    assert second.signal_row_id == first.signal_row_id

    assert db.scalar(select(func.count()).select_from(Signal)) == 1
    assert db.scalar(select(func.count()).select_from(Outbox)) == 1


def test_master_lot_info_does_not_affect_dedupe(db) -> None:
    accept_signal(db, copy.deepcopy(VALID))
    variant = copy.deepcopy(VALID)
    variant["master_lot_info"] = {"master_lot": "999.00"}
    result = accept_signal(db, variant)
    assert result.duplicate is True


def test_same_id_different_body_is_conflict(db) -> None:
    accept_signal(db, copy.deepcopy(VALID))
    tampered = copy.deepcopy(VALID)
    tampered["take_profit"] = "1.23456"
    with pytest.raises(SignalConflictError):
        accept_signal(db, tampered)


def test_money_fields_are_decimal(db) -> None:
    payload = copy.deepcopy(VALID)
    payload["signal_id"] = "sig-db-dec"
    payload["stop_loss"] = "1.075"
    accept_signal(db, payload)
    sig = db.scalar(select(Signal).where(Signal.signal_id == "sig-db-dec"))
    from decimal import Decimal

    assert isinstance(sig.stop_loss, Decimal)
