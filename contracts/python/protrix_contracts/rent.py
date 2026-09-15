"""Pure rent-wallet rules shared by settlement writers and tests."""

from __future__ import annotations

from decimal import Decimal

from protrix_contracts.money import quantize_money, to_decimal

DEFAULT_RENT_RATE = Decimal("0.10")


def validate_rent_rate(value: str | int | Decimal) -> Decimal:
    """Return a money-safe rate in the inclusive range [0, 1]."""

    rate = to_decimal(value)
    if rate < 0 or rate > 1:
        raise ValueError("rent rate must be between 0 and 1")
    return rate


def calculate_rent_due(
    net_closed_realized_pnl: str | int | Decimal,
    rent_rate: str | int | Decimal = DEFAULT_RENT_RATE,
) -> Decimal:
    """Calculate rent from net closed realized P&L.

    The caller must provide a basis that already includes commission and swap
    and excludes manual trades. Losses produce zero rent and never create a
    loss carry-forward or a rent credit.
    """

    pnl = to_decimal(net_closed_realized_pnl)
    rate = validate_rent_rate(rent_rate)
    return quantize_money(max(pnl * rate, Decimal("0")))


def signed_rent_charge(rent_due: str | int | Decimal) -> Decimal:
    """Return the negative ledger amount for a calculated rent charge."""

    due = quantize_money(rent_due)
    if due < 0:
        raise ValueError("rent due cannot be negative")
    if due == 0:
        raise ValueError("zero rent does not create a ledger charge")
    return -due
