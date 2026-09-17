"""Position sizing. Stored config is authoritative - the wire never is.

``computed_lot = clamp(multiplier, min, max) * master_lot`` rounded DOWN to the
broker lot step. All Decimal, no floats.

The actual formula now lives in ``protrix_contracts.money.compute_lot`` so the
api's client-facing "effective lot" preview (before a multiplier choice is
saved) uses the exact same computation as real execution - re-exported here
so existing ``from app.sizing import compute_lot`` call sites are unchanged.
"""

from __future__ import annotations

from protrix_contracts.money import compute_lot

__all__ = ["compute_lot"]
