"""Tests for the pure price calculation (no database)."""

from datetime import date
from decimal import Decimal

from app.services.pricing import calculate_price, rental_days

D = date(2026, 10, 10)


def test_same_day_rental_counts_as_one_day():
    assert rental_days(D, D) == 1


def test_rental_days_include_both_ends():
    assert rental_days(D, date(2026, 10, 12)) == 3


def test_total_is_sum_of_daily_prices_times_days():
    quote = calculate_price(
        [Decimal("300"), Decimal("150.50")], [Decimal("0"), Decimal("0")],
        D, date(2026, 10, 12),
    )
    assert quote.rental_days == 3
    assert quote.total_price == Decimal("1351.50")


def test_deposit_is_sum_of_deposits_and_ignores_days():
    quote = calculate_price(
        [Decimal("1"), Decimal("1")], [Decimal("1000"), Decimal("500")],
        D, date(2026, 10, 20),
    )
    assert quote.deposit == Decimal("1500.00")


def test_amounts_are_rounded_to_cents():
    quote = calculate_price([Decimal("0.333")], [Decimal("0")], D, D)
    assert quote.total_price == Decimal("0.33")
