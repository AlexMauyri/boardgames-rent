"""Tests for the pure price calculation (no database, no gRPC)."""

from decimal import Decimal

import pytest

from app.pricing.calculator import RentalLine, calculate, discount_percent


def _line(daily: str, deposit: str = "0") -> RentalLine:
    return RentalLine(daily_price=Decimal(daily), deposit=Decimal(deposit))


@pytest.mark.parametrize(
    ("days", "percent"),
    [(1, 0), (2, 0), (3, 5), (6, 5), (7, 10), (13, 10), (14, 15), (60, 15)],
)
def test_discount_tiers(days, percent):
    assert discount_percent(days) == percent


def test_short_rental_has_no_discount():
    result = calculate([_line("300"), _line("150.50")], 2)

    assert result.subtotal == Decimal("901.00")
    assert result.discount_percent == 0
    assert result.discount_amount == Decimal("0.00")
    assert result.total_price == Decimal("901.00")


def test_discount_is_taken_off_the_subtotal():
    result = calculate([_line("100")], 7)

    assert result.subtotal == Decimal("700.00")
    assert result.discount_percent == 10
    assert result.discount_amount == Decimal("70.00")
    assert result.total_price == Decimal("630.00")


def test_deposit_ignores_days_and_discount():
    result = calculate([_line("1", "1000"), _line("1", "500")], 20)

    assert result.deposit == Decimal("1500.00")


def test_amounts_are_rounded_to_cents():
    result = calculate([_line("0.333")], 3)

    assert result.subtotal == Decimal("1.00")
    assert result.discount_amount == Decimal("0.05")
    assert result.total_price == Decimal("0.95")


def test_discount_rounds_half_up():
    # 5% of 0.90 is exactly 0.045; banker's rounding would give 0.04.
    result = calculate([_line("0.30")], 3)

    assert result.subtotal == Decimal("0.90")
    assert result.discount_amount == Decimal("0.05")
    assert result.total_price == Decimal("0.85")


def test_empty_lines_are_rejected():
    with pytest.raises(ValueError, match="at least one"):
        calculate([], 3)


def test_zero_days_are_rejected():
    with pytest.raises(ValueError, match="rental_days"):
        calculate([_line("1")], 0)


def test_negative_amount_is_rejected():
    with pytest.raises(ValueError, match="negative"):
        calculate([_line("-1")], 1)
