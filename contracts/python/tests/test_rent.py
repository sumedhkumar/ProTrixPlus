from decimal import Decimal

import pytest
from protrix_contracts.rent import (
    DEFAULT_RENT_RATE,
    calculate_rent_due,
    signed_rent_charge,
    validate_rent_rate,
)


def test_default_rate_is_ten_percent() -> None:
    assert DEFAULT_RENT_RATE == Decimal("0.10")
    assert calculate_rent_due("125.00") == Decimal("12.50000000")


def test_losses_have_no_rent_or_loss_carry_forward() -> None:
    assert calculate_rent_due("-125.00") == Decimal("0E-8")
    assert calculate_rent_due("0.00") == Decimal("0E-8")


def test_explicit_rate_and_money_rounding() -> None:
    assert calculate_rent_due("10.005", "0.125") == Decimal("1.25062500")


def test_rate_is_bounded_and_float_inputs_are_rejected() -> None:
    with pytest.raises(ValueError, match="between 0 and 1"):
        validate_rent_rate("1.01")
    with pytest.raises(TypeError, match="binary float"):
        calculate_rent_due(100.0)


def test_rent_charge_is_a_negative_ledger_amount() -> None:
    assert signed_rent_charge("12.50") == Decimal("-12.50000000")
    with pytest.raises(ValueError, match="zero rent"):
        signed_rent_charge("0")
