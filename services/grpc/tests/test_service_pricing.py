"""Tests for PricingService over an in-process gRPC server (no database)."""

import grpc
import pytest

from app.generated.pricing.v1 import pricing_pb2, pricing_pb2_grpc


async def _call(port: int, request: pricing_pb2.CalculatePriceRequest):
    async with grpc.aio.insecure_channel(f"localhost:{port}") as channel:
        stub = pricing_pb2_grpc.PricingServiceStub(channel)
        return await stub.CalculatePrice(request, timeout=2.0)


def _request(days: int, *lines: tuple[str, str]):
    return pricing_pb2.CalculatePriceRequest(
        rental_days=days,
        lines=[
            pricing_pb2.RentalLine(daily_price=daily, deposit=deposit)
            for daily, deposit in lines
        ],
    )


async def test_calculates_discounted_price(grpc_server):
    resp = await _call(
        grpc_server, _request(7, ("100.00", "500.00"), ("50.00", "200.00")),
    )

    assert resp.rental_days == 7
    assert resp.subtotal == "1050.00"
    assert resp.discount_percent == 10
    assert resp.discount_amount == "105.00"
    assert resp.total_price == "945.00"
    assert resp.deposit == "700.00"


async def test_short_rental_has_no_discount(grpc_server):
    resp = await _call(grpc_server, _request(1, ("100", "0")))

    assert resp.discount_percent == 0
    assert resp.total_price == "100.00"


@pytest.mark.parametrize(
    "request_",
    [
        _request(3),
        _request(0, ("1", "1")),
        _request(3, ("abc", "1")),
        _request(3, ("1", "NaN")),
        _request(3, ("-1", "1")),
    ],
    ids=["no-lines", "zero-days", "not-a-number", "nan", "negative"],
)
async def test_invalid_input_is_rejected(grpc_server, request_):
    with pytest.raises(grpc.aio.AioRpcError) as exc:
        await _call(grpc_server, request_)

    assert exc.value.code() == grpc.StatusCode.INVALID_ARGUMENT
