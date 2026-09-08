"""Unit: canonical payload hash is stable and sensitive."""

from __future__ import annotations

from protrix_contracts.hashing import canonical_payload, canonical_payload_hash

BASE: dict = {
    "schema_version": "1.0",
    "strategy_key": "trend-rider",
    "strategy_version": "2025.09",
    "signal_id": "sig-abc-001",
    "event_time_utc": "2026-09-08T10:15:00Z",
    "action": "BUY",
    "symbol": "EURUSD",
    "timeframe": "15m",
    "position_ref": None,
    "close_fraction": None,
    "stop_loss": "1.07500",
    "take_profit": "1.09000",
}


def test_hash_is_stable_across_key_order_and_whitespace() -> None:
    reordered = {k: BASE[k] for k in reversed(list(BASE))}
    padded = {k: (f"  {v}  " if isinstance(v, str) else v) for k, v in BASE.items()}
    assert canonical_payload_hash(BASE) == canonical_payload_hash(reordered)
    assert canonical_payload_hash(BASE) == canonical_payload_hash(padded)


def test_hash_ignores_master_lot_info() -> None:
    with_info = dict(BASE, master_lot_info={"master_lot": "9.99"})
    assert canonical_payload_hash(BASE) == canonical_payload_hash(with_info)


def test_hash_changes_when_a_semantic_field_changes() -> None:
    changed = dict(BASE, take_profit="1.09500")
    assert canonical_payload_hash(BASE) != canonical_payload_hash(changed)


def test_hash_has_algorithm_prefix() -> None:
    assert canonical_payload_hash(BASE).startswith("sha256:")


def test_canonical_payload_is_pure_projection() -> None:
    canon = canonical_payload(dict(BASE, junk="x"))
    assert "junk" not in canon
    assert canon["signal_id"] == "sig-abc-001"
