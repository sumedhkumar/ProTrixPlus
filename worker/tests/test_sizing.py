"""Unit: sizing is Decimal, clamped, and rounds DOWN."""

from __future__ import annotations

from decimal import Decimal

from app.sizing import compute_lot


def test_basic_multiplier() -> None:
    lot = compute_lot(
        master_lot=Decimal("1.00"),
        multiplier=Decimal("1.5"),
        multiplier_min=Decimal("0.5"),
        multiplier_max=Decimal("2.0"),
    )
    assert lot == Decimal("1.50")
    assert isinstance(lot, Decimal)


def test_multiplier_clamped_to_bounds() -> None:
    lot = compute_lot(
        master_lot=Decimal("2.00"),
        multiplier=Decimal("9.9"),
        multiplier_min=Decimal("0.5"),
        multiplier_max=Decimal("2.0"),
    )
    assert lot == Decimal("4.00")  # 2.00 * clamp(9.9 -> 2.0)


def test_rounds_down_never_up() -> None:
    lot = compute_lot(
        master_lot=Decimal("1.00"),
        multiplier=Decimal("1.019"),
        multiplier_min=Decimal("0.5"),
        multiplier_max=Decimal("2.0"),
    )
    assert lot == Decimal("1.01")  # 1.019 -> 1.01, not 1.02


def test_floors_at_one_step() -> None:
    lot = compute_lot(
        master_lot=Decimal("0.001"),
        multiplier=Decimal("0.5"),
        multiplier_min=Decimal("0.5"),
        multiplier_max=Decimal("2.0"),
    )
    assert lot == Decimal("0.01")
