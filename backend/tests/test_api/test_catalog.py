"""Tests for /api/v1/catalog/*."""

from app.schemas import CategoryCreate
from app.services import create_category, deactivate_pickup_point
from tests.helpers import make_copy, make_game, make_point

URL = "/api/v1/catalog"


async def test_categories_public_and_cached(http, session):
    await create_category(session, CategoryCreate(name="Strategy"))

    r1 = await http.get(f"{URL}/categories")
    assert r1.status_code == 200
    assert [c["name"] for c in r1.json()] == ["Strategy"]

    # Bypasses the admin API, so nothing invalidates the cached list.
    await create_category(session, CategoryCreate(name="Coop"))
    r2 = await http.get(f"{URL}/categories")
    assert r2.json() == r1.json()


async def test_pickup_points_only_active(http, session):
    await make_point(session, "Center")
    north = await make_point(session, "North")
    await deactivate_pickup_point(session, north)

    r = await http.get(f"{URL}/pickup-points")
    assert r.status_code == 200
    assert [p["name"] for p in r.json()] == ["Center"]


async def test_games_list_and_filter(http, session):
    await make_game(session, "Dune")

    r = await http.get(f"{URL}/games")
    assert r.status_code == 200
    assert [g["title"] for g in r.json()] == ["Dune"]
    assert "cover_key" not in r.json()[0]

    r = await http.get(f"{URL}/games", params={"players": 6})
    assert r.json() == []


async def test_games_rejects_bad_filter(http):
    r = await http.get(f"{URL}/games", params={"players": 0})
    assert r.status_code == 422


async def test_game_detail(http, session):
    game_id = await make_game(session, "Dune")

    r = await http.get(f"{URL}/games/{game_id}")
    assert r.status_code == 200
    assert r.json()["title"] == "Dune"


async def test_game_detail_404(http, session):
    r = await http.get(f"{URL}/games/999999")
    assert r.status_code == 404


async def test_search_is_not_cached(http, session):
    point = await make_point(session)
    game = await make_game(session)
    params = {"pickup_point_id": point}

    r1 = await http.get(f"{URL}/search", params=params)
    assert r1.status_code == 200
    assert r1.json() == []

    # A new free box must show up immediately.
    await make_copy(session, game, point, "INV-1")
    r2 = await http.get(f"{URL}/search", params=params)
    assert len(r2.json()) == 1
    assert r2.json()[0]["free_at_point"] == 1


async def test_search_requires_point(http, session):
    r = await http.get(f"{URL}/search")
    assert r.status_code == 422


async def test_search_unknown_point_404(http, session):
    r = await http.get(f"{URL}/search", params={"pickup_point_id": 999999})
    assert r.status_code == 404


async def test_search_inactive_point_422(http, session):
    point = await make_point(session)
    await deactivate_pickup_point(session, point)

    r = await http.get(f"{URL}/search", params={"pickup_point_id": point})
    assert r.status_code == 422
