"""Rental price calculation.

`calculate_price` is a pure function with no database access and no
discount. The gRPC pricing service applies the real rules; callers depend
only on `PriceQuote` and `PriceCalculator`, so either can serve a request.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol

_CENT = Decimal("0.01")


@dataclass(frozen=True)
class PriceQuote:
    """The cost of a rental.

    Attributes:
        rental_days: Number of rental days, both end dates included.
        total_price: Rental cost for all boxes over all days, after the
            discount.
        deposit: Refundable deposit for all boxes.
        discount_percent: Duration discount already taken off, 0 if none.
        discount_amount: Money taken off the undiscounted cost.
    """

    rental_days: int
    total_price: Decimal
    deposit: Decimal
    discount_percent: int = 0
    discount_amount: Decimal = Decimal("0.00")

    @property
    def subtotal(self) -> Decimal:
        """Rental cost before the discount."""
        return self.total_price + self.discount_amount


class PriceCalculator(Protocol):
    """Anything that can price a rental asynchronously, e.g. the gRPC client."""

    async def calculate_price(
        self,
        daily_prices: Sequence[Decimal],
        deposits: Sequence[Decimal],
        start_date: date,
        end_date: date,
    ) -> PriceQuote:
        """Price a rental of several boxes."""


def rental_days(start_date: date, end_date: date) -> int:
    """Count rental days with both end dates included.

    Args:
        start_date: First day of the rental.
        end_date: Last day of the rental, not before `start_date`.

    Returns:
        At least 1: a same-day rental counts as one day.
    """
    return (end_date - start_date).days + 1


def calculate_price(
    daily_prices: Sequence[Decimal],
    deposits: Sequence[Decimal],
    start_date: date,
    end_date: date,
) -> PriceQuote:
    """Price a rental of several boxes.

    No discount is applied; the total is the sum of daily tariffs times days.

    Args:
        daily_prices: Daily tariff of each rented box.
        deposits: Deposit of each rented box.
        start_date: First day of the rental.
        end_date: Last day of the rental.

    Returns:
        The quote, rounded to cents.
    """
    days = rental_days(start_date, end_date)
    total = (sum(daily_prices, Decimal("0")) * days).quantize(_CENT)
    deposit = sum(deposits, Decimal("0")).quantize(_CENT)
    return PriceQuote(rental_days=days, total_price=total, deposit=deposit)
