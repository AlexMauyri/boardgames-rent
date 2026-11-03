"""Tests for pricing through an injected price calculator (the gRPC seam)."""

from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.db.models import Order
from app.services import (
    NotFoundError,
    ServiceUnavailableError,
    create_order,
    quote_order,
)
from app.services.pricing import PriceQuote
from tests.helpers import (
    make_client,
    make_copy,
    make_game,
    make_point,
    order_request,
)


class _StubPricing:
    """Records its arguments and returns a fixed 10% discount."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def calculate_price(self, daily_prices, deposits, start_date, end_date):
        self.calls.append((list(daily_prices), list(deposits)))
        return PriceQuote(
            rental_days=(end_date - start_date).days + 1,
            total_price=Decimal("900.00"),
            deposit=Decimal("1000.00"),
            discount_percent=10,
            discount_amount=Decimal("100.00"),
        )


class _BrokenPricing:
    async def calculate_price(self, *args):
        raise ServiceUnavailableError("Pricing service unavailable")


async def _setup(session):
    point = await make_point(session)
    game = await make_game(session, daily="300", deposit="1000")
    await make_copy(session, game, point, "INV-1")
    client = await make_client(session)
    return point, game, client


async def test_order_is_priced_by_the_given_service(session):
    point, game, client = await _setup(session)
    pricing = _StubPricing()

    order = await create_order(
        session, client, order_request(point, [game]), pricing=pricing,
    )

    assert order.total_price == Decimal("900.00")
    assert order.deposit_paid == Decimal("1000.00")
    assert pricing.calls == [([Decimal("300.00")], [Decimal("1000.00")])]


async def test_every_requested_box_is_priced(session):
    point = await make_point(session)
    game = await make_game(session, daily="300", deposit="1000")
    await make_copy(session, game, point, "INV-1")
    await make_copy(session, game, point, "INV-2")
    client = await make_client(session)
    pricing = _StubPricing()

    await create_order(
        session, client, order_request(point, [game, game]), pricing=pricing,
    )

    daily, deposits = pricing.calls[0]
    assert daily == [Decimal("300.00")] * 2
    assert deposits == [Decimal("1000.00")] * 2


async def test_unavailable_pricing_service_places_no_order(session):
    point, game, client = await _setup(session)

    with pytest.raises(ServiceUnavailableError):
        await create_order(
            session, client, order_request(point, [game]),
            pricing=_BrokenPricing(),
        )

    assert await session.scalar(select(func.count()).select_from(Order)) == 0


async def test_without_a_service_the_local_undiscounted_price_is_used(session):
    point, game, client = await _setup(session)

    order = await create_order(session, client, order_request(point, [game]))

    assert order.total_price == Decimal("900.00")  # 300 * 3 days, no discount


async def test_quote_returns_the_breakdown(session):
    point, game, _ = await _setup(session)

    quote = await quote_order(
        session, order_request(point, [game]), pricing=_StubPricing(),
    )

    assert quote.rental_days == 3
    assert quote.subtotal == Decimal("1000.00")
    assert quote.discount_percent == 10
    assert quote.discount_amount == Decimal("100.00")
    assert quote.total_price == Decimal("900.00")
    assert quote.deposit == Decimal("1000.00")


async def test_quote_does_not_place_an_order(session):
    point, game, _ = await _setup(session)

    await quote_order(session, order_request(point, [game]), pricing=_StubPricing())

    assert await session.scalar(select(func.count()).select_from(Order)) == 0


async def test_quote_unknown_game(session):
    point, _, _ = await _setup(session)

    with pytest.raises(NotFoundError):
        await quote_order(session, order_request(point, [999999]))
