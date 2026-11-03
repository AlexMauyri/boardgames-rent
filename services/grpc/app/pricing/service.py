"""gRPC pricing servicer."""

import logging
from decimal import Decimal, InvalidOperation

import grpc

from app.generated.pricing.v1 import pricing_pb2, pricing_pb2_grpc
from app.pricing.calculator import RentalLine, calculate

logger = logging.getLogger(__name__)


def _parse_money(value: str) -> Decimal:
    """Parse a finite decimal string, or raise ``ValueError``."""
    try:
        amount = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"not a decimal amount: {value!r}") from exc
    if not amount.is_finite():
        raise ValueError(f"not a finite amount: {value!r}")
    return amount


class PricingServicer(pricing_pb2_grpc.PricingServiceServicer):
    """Serves PricingService. Stateless: it never touches the database."""

    async def CalculatePrice(
        self,
        request: pricing_pb2.CalculatePriceRequest,
        context: grpc.aio.ServicerContext,
    ) -> pricing_pb2.CalculatePriceResponse:
        """Price a rental.

        Algorithm:
            1. Parse the decimal strings of every line
               (``INVALID_ARGUMENT`` on malformed or negative amounts).
            2. Subtotal = sum of daily tariffs x ``rental_days``.
            3. Apply the duration discount tier (see
               ``app.pricing.calculator.DISCOUNT_TIERS``).
            4. Deposit = sum of box deposits, independent of duration.
        """
        try:
            lines = [
                RentalLine(
                    daily_price=_parse_money(line.daily_price),
                    deposit=_parse_money(line.deposit),
                )
                for line in request.lines
            ]
            result = calculate(lines, request.rental_days)
        except ValueError as exc:
            logger.warning("CalculatePrice rejected: %s", exc)
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(exc))

        logger.info(
            "CalculatePrice boxes=%s days=%s subtotal=%s discount=%s%% "
            "total=%s deposit=%s",
            len(lines), result.rental_days, result.subtotal,
            result.discount_percent, result.total_price, result.deposit,
        )
        return pricing_pb2.CalculatePriceResponse(
            rental_days=result.rental_days,
            subtotal=str(result.subtotal),
            discount_percent=result.discount_percent,
            discount_amount=str(result.discount_amount),
            total_price=str(result.total_price),
            deposit=str(result.deposit),
        )
