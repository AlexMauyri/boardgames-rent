"""Rental price calculation with a duration discount.

Pure functions, no database and no gRPC imports. The rules are:

* the subtotal is the sum of daily tariffs times the number of days;
* a rental of at least ``N`` days earns the discount of the highest
  matching tier of ``DISCOUNT_TIERS``;
* the deposit is the sum of box deposits and does not depend on the
  duration or the discount.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

_CENT = Decimal("0.01")
_HUNDRED = Decimal(100)

# (minimum rental days, discount percent), longest rental first.
DISCOUNT_TIERS: tuple[tuple[int, int], ...] = (
    (14, 15),
    (7, 10),
    (3, 5),
)


@dataclass(frozen=True)
class RentalLine:
    """One rented box.

    Attributes:
        daily_price: Tariff per day.
        deposit: Refundable deposit.
    """

    daily_price: Decimal
    deposit: Decimal


@dataclass(frozen=True)
class PriceBreakdown:
    """Result of pricing a rental; all amounts are rounded to cents.

    Attributes:
        rental_days: Rental duration, both end dates included.
        subtotal: Cost before the discount.
        discount_percent: Applied discount, 0 when the rental is too short.
        discount_amount: Money taken off the subtotal.
        total_price: Subtotal minus the discount.
        deposit: Total refundable deposit.
    """

    rental_days: int
    subtotal: Decimal
    discount_percent: int
    discount_amount: Decimal
    total_price: Decimal
    deposit: Decimal


def discount_percent(rental_days: int) -> int:
    """Return the discount earned by a rental of ``rental_days`` days."""
    for min_days, percent in DISCOUNT_TIERS:
        if rental_days >= min_days:
            return percent
    return 0


def calculate(lines: Sequence[RentalLine], rental_days: int) -> PriceBreakdown:
    """Price a rental of several boxes.

    Args:
        lines: The rented boxes, at least one.
        rental_days: Rental duration in days, at least 1.

    Returns:
        The full price breakdown.

    Raises:
        ValueError: ``lines`` is empty, ``rental_days`` is below 1, or an
            amount is negative.
    """
    if not lines:
        raise ValueError("at least one rental line is required")
    if rental_days < 1:
        raise ValueError("rental_days must be at least 1")
    if any(line.daily_price < 0 or line.deposit < 0 for line in lines):
        raise ValueError("prices and deposits must not be negative")

    daily_sum = sum((line.daily_price for line in lines), Decimal(0))
    subtotal = (daily_sum * rental_days).quantize(_CENT, ROUND_HALF_UP)
    percent = discount_percent(rental_days)
    discount = (subtotal * percent / _HUNDRED).quantize(_CENT, ROUND_HALF_UP)
    deposit = sum((line.deposit for line in lines), Decimal(0)).quantize(
        _CENT, ROUND_HALF_UP,
    )
    return PriceBreakdown(
        rental_days=rental_days,
        subtotal=subtotal,
        discount_percent=percent,
        discount_amount=discount,
        total_price=subtotal - discount,
        deposit=deposit,
    )
