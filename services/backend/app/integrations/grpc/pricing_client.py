"""Client for the pricing gRPC service."""

import logging
from collections.abc import Sequence
from datetime import date
from decimal import Decimal

import grpc
import grpc.aio

from app.config import settings
from app.grpc_generated.pricing.v1 import pricing_pb2, pricing_pb2_grpc
from app.services.exceptions import ServiceUnavailableError
from app.services.pricing import PriceQuote, rental_days

logger = logging.getLogger(__name__)


class PricingClient:
    """Typed stub for ``PricingService`` over a shared channel."""

    def __init__(self, channel: grpc.aio.Channel) -> None:
        self._stub = pricing_pb2_grpc.PricingServiceStub(channel)

    async def calculate_price(
        self,
        daily_prices: Sequence[Decimal],
        deposits: Sequence[Decimal],
        start_date: date,
        end_date: date,
    ) -> PriceQuote:
        """Price a rental; same arguments as ``pricing.calculate_price``.

        Raises:
            ServiceUnavailableError: The gRPC call failed. A quote is never
                guessed locally: the discount rules live in the service, and
                a silent fallback would charge a different amount.
        """
        days = rental_days(start_date, end_date)
        request = pricing_pb2.CalculatePriceRequest(
            rental_days=days,
            lines=[
                pricing_pb2.RentalLine(
                    daily_price=str(daily), deposit=str(deposit),
                )
                for daily, deposit in zip(daily_prices, deposits, strict=True)
            ],
        )
        try:
            response = await self._stub.CalculatePrice(
                request, timeout=settings.grpc_timeout_seconds,
            )
        except grpc.aio.AioRpcError as exc:
            logger.warning("gRPC CalculatePrice failed code=%s", exc.code())
            raise ServiceUnavailableError("Pricing service unavailable") from exc

        return PriceQuote(
            rental_days=response.rental_days,
            total_price=Decimal(response.total_price),
            deposit=Decimal(response.deposit),
            discount_percent=response.discount_percent,
            discount_amount=Decimal(response.discount_amount),
        )
