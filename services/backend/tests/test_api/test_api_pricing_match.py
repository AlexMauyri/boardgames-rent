"""Tests for POST /orders/quote, order pricing and GET /catalog/match.

The gRPC clients are replaced by stubs on ``app.state``; the database is the
real test database.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.auth.jwt import create_access_token
from app.main import app as fastapi_app
from app.services.catalog import RankedGame
from app.services.exceptions import ServiceUnavailableError
from app.services.pricing import PriceQuote
from tests.helpers import make_client, make_copy, make_game, make_point

QUOTE = "/api/v1/orders/quote"
ORDERS = "/api/v1/orders"
MATCH = "/api/v1/catalog/match"


class _StubPricing:
    async def calculate_price(self, daily_prices, deposits, start_date, end_date):
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


class _StubRanker:
    def __init__(self, ranked: list[RankedGame]) -> None:
        self.ranked = ranked

    async def rank_games(self, *args):
        return self.ranked


def _headers(client_id: int) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(client_id, 'CLIENT')}"}


def _payload(point_id: int, game_ids: list[int], days: int = 7) -> dict:
    start = date.today() + timedelta(days=1)
    return {
        "pickup_point_id": point_id,
        "start_date": start.isoformat(),
        "end_date": (start + timedelta(days=days - 1)).isoformat(),
        "game_ids": game_ids,
    }


@pytest.fixture
def stub_pricing(monkeypatch):
    stub = _StubPricing()
    monkeypatch.setattr(fastapi_app.state, "pricing_client", stub, raising=False)
    return stub


async def _stocked(session):
    point = await make_point(session)
    game = await make_game(session)
    await make_copy(session, game, point, "INV-1")
    client = await make_client(session)
    return point, game, client


# --- POST /orders/quote --------------------------------------------------


async def test_quote_returns_discount_breakdown(http, session, stub_pricing):
    point, game, client = await _stocked(session)

    r = await http.post(QUOTE, json=_payload(point, [game]), headers=_headers(client))

    assert r.status_code == 200
    body = r.json()
    assert body["rental_days"] == 7
    assert body["discount_percent"] == 10
    assert Decimal(body["subtotal"]) == Decimal("1000.00")
    assert Decimal(body["discount_amount"]) == Decimal("100.00")
    assert Decimal(body["total_price"]) == Decimal("900.00")
    assert Decimal(body["deposit"]) == Decimal("1000.00")


async def test_quote_requires_a_token(http, session):
    r = await http.post(QUOTE, json=_payload(1, [1]))

    assert r.status_code == 401


async def test_quote_unknown_game_404(http, session, stub_pricing):
    point, _, client = await _stocked(session)

    r = await http.post(QUOTE, json=_payload(point, [999999]), headers=_headers(client))

    assert r.status_code == 404


async def test_quote_503_when_pricing_service_is_down(http, session, monkeypatch):
    point, game, client = await _stocked(session)
    monkeypatch.setattr(
        fastapi_app.state, "pricing_client", _BrokenPricing(), raising=False,
    )

    r = await http.post(QUOTE, json=_payload(point, [game]), headers=_headers(client))

    assert r.status_code == 503


# --- POST /orders -------------------------------------------------------


async def test_order_is_priced_by_the_pricing_service(http, session, stub_pricing):
    point, game, client = await _stocked(session)

    r = await http.post(ORDERS, json=_payload(point, [game]), headers=_headers(client))

    assert r.status_code == 201
    assert Decimal(r.json()["total_price"]) == Decimal("900.00")


async def test_order_503_when_pricing_service_is_down(http, session, monkeypatch):
    point, game, client = await _stocked(session)
    monkeypatch.setattr(
        fastapi_app.state, "pricing_client", _BrokenPricing(), raising=False,
    )

    r = await http.post(ORDERS, json=_payload(point, [game]), headers=_headers(client))

    assert r.status_code == 503
    listing = await http.get(ORDERS, headers=_headers(client))
    assert listing.json() == []


# --- GET /catalog/match -------------------------------------------------


async def test_match_returns_the_ranked_games(http, session, monkeypatch):
    point = await make_point(session)
    first = await make_game(session, "First")
    second = await make_game(session, "Second")
    await make_copy(session, first, point, "I1")
    await make_copy(session, second, point, "I2")
    monkeypatch.setattr(
        fastapi_app.state, "matching_client",
        _StubRanker([
            RankedGame(second, 0.9, "fits_meeting"),
            RankedGame(first, 0.5, "needs_delivery"),
        ]),
        raising=False,
    )

    r = await http.get(
        MATCH, params={"pickup_point_id": point, "players": 4, "playtime_max": 120},
    )

    assert r.status_code == 200
    body = r.json()
    assert [item["game"]["id"] for item in body] == [second, first]
    assert body[0]["score"] == 0.9
    assert body[0]["reason"] == "fits_meeting"
    assert body[0]["free_at_point"] == 1
    assert body[0]["free_elsewhere"] == 0


async def test_match_falls_back_to_a_filter_without_the_service(http, session):
    point = await make_point(session)
    game = await make_game(session)  # 2-4 players, 90 minutes
    await make_copy(session, game, point, "I1")
    other = await make_game(session, "Other")
    await make_copy(session, other, point, "I2")

    r = await http.get(
        MATCH, params={"pickup_point_id": point, "players": 3, "playtime_max": 120},
    )

    assert r.status_code == 200
    assert {item["reason"] for item in r.json()} == {"fallback_filter"}
    assert {item["game"]["id"] for item in r.json()} == {game, other}


async def test_match_unknown_point_404(http, session):
    r = await http.get(
        MATCH, params={"pickup_point_id": 999999, "players": 4, "playtime_max": 60},
    )

    assert r.status_code == 404


@pytest.mark.parametrize("params", [{"players": 0, "playtime_max": 60}, {"players": 4}])
async def test_match_validates_parameters(http, session, params):
    point = await make_point(session)

    r = await http.get(MATCH, params={"pickup_point_id": point, **params})

    assert r.status_code == 422
