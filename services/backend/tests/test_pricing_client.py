"""Tests for the pricing gRPC client against an in-process fake server."""

from datetime import date
from decimal import Decimal

import grpc
import pytest
import pytest_asyncio

from app.config import settings
from app.grpc_generated.pricing.v1 import pricing_pb2, pricing_pb2_grpc
from app.integrations.grpc.pricing_client import PricingClient
from app.services.exceptions import ServiceUnavailableError


class _FakePricing(pricing_pb2_grpc.PricingServiceServicer):
    """Records the last request and answers with a fixed 10% discount."""

    def __init__(self) -> None:
        self.last_request: pricing_pb2.CalculatePriceRequest | None = None

    async def CalculatePrice(self, request, context):
        self.last_request = request
        return pricing_pb2.CalculatePriceResponse(
            rental_days=request.rental_days,
            subtotal="1050.00",
            discount_percent=10,
            discount_amount="105.00",
            total_price="945.00",
            deposit="700.00",
        )


@pytest_asyncio.fixture
async def fake_pricing():
    servicer = _FakePricing()
    server = grpc.aio.server()
    pricing_pb2_grpc.add_PricingServiceServicer_to_server(servicer, server)
    port = server.add_insecure_port("localhost:0")
    await server.start()
    async with grpc.aio.insecure_channel(f"localhost:{port}") as channel:
        yield PricingClient(channel), servicer
    await server.stop(grace=0)


async def test_sends_lines_and_days_and_maps_the_quote(fake_pricing):
    client, servicer = fake_pricing

    quote = await client.calculate_price(
        [Decimal("100"), Decimal("50.50")],
        [Decimal("500"), Decimal("200")],
        date(2026, 10, 1),
        date(2026, 10, 7),
    )

    request = servicer.last_request
    assert request.rental_days == 7
    assert [(l.daily_price, l.deposit) for l in request.lines] == [
        ("100", "500"), ("50.50", "200"),
    ]
    assert quote.rental_days == 7
    assert quote.total_price == Decimal("945.00")
    assert quote.deposit == Decimal("700.00")
    assert quote.discount_percent == 10
    assert quote.discount_amount == Decimal("105.00")
    assert quote.subtotal == Decimal("1050.00")


async def test_unreachable_server_raises_service_unavailable(monkeypatch):
    monkeypatch.setattr(settings, "grpc_timeout_seconds", 0.2)
    async with grpc.aio.insecure_channel("127.0.0.1:1") as channel:
        client = PricingClient(channel)
        with pytest.raises(ServiceUnavailableError):
            await client.calculate_price(
                [Decimal("1")], [Decimal("1")],
                date(2026, 10, 1), date(2026, 10, 1),
            )
