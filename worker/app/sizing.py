"""Position sizing. Stored config is authoritative - the wire never is.

``computed_lot = clamp(multiplier, min, max) * master_lot`` rounded DOWN to the
broker lot step. All Decimal, no floats.
"""

from __future__ import annotations

from decimal import Decimal

from protrix_contracts.money import LOT_QUANT, clamp, quantize_lot


def compute_lot(
    *, master_lot: Decimal, multiplier: Decimal, multiplier_min: Decimal, multiplier_max: Decimal
) -> Decimal:
    effective = clamp(multiplier, multiplier_min, multiplier_max)
    raw = master_lot * effective
    lot = quantize_lot(raw)
    if lot < LOT_QUANT:
        # Never emit a zero/sub-minimum lot; floor at one step.
        lot = LOT_QUANT
    return lot
