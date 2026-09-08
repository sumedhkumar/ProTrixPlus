"""Deterministic canonical hashing of a webhook payload.

The hash is the basis of the signal dedupe/idempotency guard. It must be:

* **stable** - the same semantic payload always hashes to the same value,
  regardless of key order or insignificant whitespace on the wire;
* **sensitive** - any change to a semantic field changes the hash.

Only the frozen semantic fields participate. ``master_lot_info`` is excluded on
purpose: it is informational only, so two otherwise-identical signals that differ
only in ``master_lot_info`` are the *same* signal for dedupe purposes.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

# Fields that define the identity of a signal. Order here is irrelevant; we sort.
CANONICAL_FIELDS: tuple[str, ...] = (
    "schema_version",
    "strategy_key",
    "strategy_version",
    "signal_id",
    "event_time_utc",
    "action",
    "symbol",
    "timeframe",
    "position_ref",
    "close_fraction",
    "stop_loss",
    "take_profit",
)


def _normalize(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):  # pragma: no cover - contract forbids wire floats
        raise TypeError("float encountered in payload; money/price fields must be strings")
    return str(value).strip()


def canonical_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Project ``payload`` down to its normalized canonical fields."""
    return {field: _normalize(payload.get(field)) for field in CANONICAL_FIELDS}


def canonical_payload_hash(payload: dict[str, Any]) -> str:
    """Return the hex SHA-256 of the canonical JSON encoding of ``payload``."""
    canonical = canonical_payload(payload)
    encoded = json.dumps(
        canonical,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()
