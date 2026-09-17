"""Decimal helpers with explicit, auditable rounding.

Rules for the whole system:

* Money / prices / rates use :data:`MONEY_QUANT` and banker's rounding
  (``ROUND_HALF_EVEN``).
* Lot sizes use :data:`LOT_QUANT` and always round **down** (``ROUND_DOWN``) so a
  computed size can never exceed what the inputs justify.
* Values enter as strings (or Decimals). ``float`` is never accepted - passing a
  float raises ``TypeError`` - because the precision is already gone by then.
"""

from __future__ import annotations

from decimal import ROUND_DOWN, ROUND_HALF_EVEN, Decimal, InvalidOperation
from typing import Final

MONEY_QUANT: Final = Decimal("0.00000001")  # 8 dp is enough for FX prices in S0
LOT_QUANT: Final = Decimal("0.01")  # standard MT5 min lot step
FRACTION_QUANT: Final = Decimal("0.0001")


def to_decimal(value: str | int | Decimal) -> Decimal:
    """Coerce a *non-float* value to :class:`~decimal.Decimal`.

    ``float`` is rejected on purpose.
    """
    if isinstance(value, float):  # pragma: no cover - defensive
        raise TypeError("refusing to build a Decimal from a binary float; pass a string")
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except InvalidOperation as exc:  # pragma: no cover - defensive
        raise ValueError(f"not a valid decimal literal: {value!r}") from exc


def quantize_money(value: str | int | Decimal) -> Decimal:
    return to_decimal(value).quantize(MONEY_QUANT, rounding=ROUND_HALF_EVEN)


def quantize_lot(value: str | int | Decimal) -> Decimal:
    """Round a lot size **down** to the broker lot step."""
    return to_decimal(value).quantize(LOT_QUANT, rounding=ROUND_DOWN)


def quantize_fraction(value: str | int | Decimal) -> Decimal:
    return to_decimal(value).quantize(FRACTION_QUANT, rounding=ROUND_HALF_EVEN)


def clamp(value: Decimal, low: Decimal, high: Decimal) -> Decimal:
    if low > high:  # pragma: no cover - defensive
        raise ValueError("clamp bounds inverted")
    return max(low, min(high, value))


def compute_lot(
    *, master_lot: Decimal, multiplier: Decimal, multiplier_min: Decimal, multiplier_max: Decimal
) -> Decimal:
    """``effective = clamp(multiplier, min, max); lot = floor(master_lot * effective)``.

    Single source of truth for lot sizing, shared by the worker (actual
    execution) and the api (client-facing "effective lot" preview before
    saving a multiplier choice) so the preview can never drift from what
    actually gets traded.
    """
    effective = clamp(multiplier, multiplier_min, multiplier_max)
    raw = master_lot * effective
    lot = quantize_lot(raw)
    if lot < LOT_QUANT:
        # Never emit a zero/sub-minimum lot; floor at one step.
        lot = LOT_QUANT
    return lot
