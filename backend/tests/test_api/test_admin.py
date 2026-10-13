"""Tests for /api/v1/admin/*."""

from unittest.mock import MagicMock

import pytest

from app.api.deps import get_storage_client
from app.auth.jwt import create_access_token
from app.schemas import CategoryCreate
from app.services import create_category
from tests.helpers import (
    make_client,
    make_copy,
    make_employee,
    make_game,
    make_manager,
    make_point,
)

URL = "/api/v1/admin"
CATALOG = "/api/v1/catalog"

GAME = {
    "title": "Root",
    "min_players": 2,
    "max_players": 4,
    "playtime_minutes": 90,
    "daily_price": "250",
    "deposit_price": "1500",
}


def _headers(user_id: int, role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user_id, role)}"}


@pytest.fixture
async def admin(session) -> dict[str, str]:
    admin_id = await make_employee(session, "ADMIN", "admin@test.io")
    return _headers(admin_id, "ADMIN")


# --- access ------------------------------------------------------------


async def test_requires_token(http, session):
    r = await http.get(f"{URL}/employees")
    assert r.status_code == 401


async def test_manager_forbidden(http, session):
    point = await make_point(session)
    manager = await make_manager(session, point)

    r = await http.get(f"{URL}/employees", headers=_headers(manager, "MANAGER"))
    assert r.status_code == 403


async def test_client_forbidden(http, session):
    client = await make_client(session)

    r = await http.post(
        f"{URL}/categories", json={"name": "X"},
        headers=_headers(client, "CLIENT"),
    )
    assert r.status_code == 403


# --- categories --------------------------------------------------------


async def test_category_crud_refreshes_catalog(http, session, admin):
    assert (await http.get(f"{CATALOG}/categories")).json() == []

    r = await http.post(f"{URL}/categories", json={"name": "Coop"}, headers=admin)
    assert r.status_code == 201
    cat_id = r.json()["id"]
    assert [c["name"] for c in (await http.get(f"{CATALOG}/categories")).json()] == ["Coop"]

    r = await http.put(
        f"{URL}/categories/{cat_id}", json={"name": "Co-op"}, headers=admin,
    )
    assert r.status_code == 200
    assert [c["name"] for c in (await http.get(f"{CATALOG}/categories")).json()] == ["Co-op"]

    r = await http.delete(f"{URL}/categories/{cat_id}", headers=admin)
    assert r.status_code == 204
    assert (await http.get(f"{CATALOG}/categories")).json() == []

    r = await http.delete(f"{URL}/categories/{cat_id}", headers=admin)
    assert r.status_code == 404


async def test_category_duplicate_409(http, session, admin):
    await create_category(session, CategoryCreate(name="Coop"))

    r = await http.post(f"{URL}/categories", json={"name": "Coop"}, headers=admin)
    assert r.status_code == 409


async def test_category_delete_refreshes_filtered_games(http, session, admin):
    cat = await create_category(session, CategoryCreate(name="Coop"))
    r = await http.post(
        f"{URL}/games", json={**GAME, "category_ids": [cat.id]}, headers=admin,
    )
    assert r.status_code == 201

    params = {"category_id": cat.id}
    assert len((await http.get(f"{CATALOG}/games", params=params)).json()) == 1

    await http.delete(f"{URL}/categories/{cat.id}", headers=admin)
    assert (await http.get(f"{CATALOG}/games", params=params)).json() == []


# --- clients -----------------------------------------------------------


async def test_deactivate_client_blocks_tokens(http, session, admin):
    client = await make_client(session)
    client_headers = _headers(client, "CLIENT")
    assert (await http.get("/api/v1/orders", headers=client_headers)).status_code == 200

    r = await http.post(f"{URL}/clients/{client}/deactivate", headers=admin)
    assert r.status_code == 200
    assert r.json()["is_active"] is False
    assert (await http.get("/api/v1/orders", headers=client_headers)).status_code == 401

    r = await http.post(f"{URL}/clients/{client}/activate", headers=admin)
    assert r.json()["is_active"] is True
    assert (await http.get("/api/v1/orders", headers=client_headers)).status_code == 200


async def test_activate_unknown_client_404(http, session, admin):
    r = await http.post(f"{URL}/clients/999999/activate", headers=admin)
    assert r.status_code == 404


# --- employees ---------------------------------------------------------


async def test_create_and_list_employees(http, session, admin):
    point = await make_point(session)
    body = {
        "email": "m@test.io", "password": "secret1", "full_name": "M",
        "phone": "+7", "role": "MANAGER", "pickup_point_id": point,
    }

    r = await http.post(f"{URL}/employees", json=body, headers=admin)
    assert r.status_code == 201
    assert "password" not in r.json()
    assert "password_hash" not in r.json()

    r = await http.post(f"{URL}/employees", json=body, headers=admin)
    assert r.status_code == 409

    r = await http.get(f"{URL}/employees", params={"role": "MANAGER"}, headers=admin)
    assert [e["email"] for e in r.json()] == ["m@test.io"]

    r = await http.get(f"{URL}/employees", params={"role": "BOSS"}, headers=admin)
    assert r.status_code == 422


async def test_manager_without_point_422(http, session, admin):
    body = {
        "email": "m@test.io", "password": "secret1", "full_name": "M",
        "phone": "+7", "role": "MANAGER",
    }
    r = await http.post(f"{URL}/employees", json=body, headers=admin)
    assert r.status_code == 422


async def test_update_employee(http, session, admin):
    courier = await make_employee(session, "COURIER", "c@test.io")

    r = await http.put(
        f"{URL}/employees/{courier}", json={"full_name": "Fast"}, headers=admin,
    )
    assert r.status_code == 200
    assert r.json()["full_name"] == "Fast"

    r = await http.put(
        f"{URL}/employees/{courier}", json={"role": "MANAGER"}, headers=admin,
    )
    assert r.status_code == 422


async def test_change_role(http, session, admin):
    point = await make_point(session)
    courier = await make_employee(session, "COURIER", "c@test.io")
    role_url = f"{URL}/employees/{courier}/role"

    r = await http.put(role_url, params={"role": "MANAGER"}, headers=admin)
    assert r.status_code == 422

    r = await http.put(
        role_url, params={"role": "MANAGER", "pickup_point_id": point},
        headers=admin,
    )
    assert r.status_code == 200
    assert r.json()["role"] == "MANAGER"
    assert r.json()["pickup_point_id"] == point

    r = await http.put(role_url, params={"role": "COURIER"}, headers=admin)
    assert r.json()["pickup_point_id"] is None


async def test_assign_manager_to_point(http, session, admin):
    center = await make_point(session, "Center")
    north = await make_point(session, "North")
    manager = await make_manager(session, center)
    courier = await make_employee(session, "COURIER", "c@test.io")

    r = await http.put(
        f"{URL}/employees/{manager}/pickup-point",
        params={"pickup_point_id": north}, headers=admin,
    )
    assert r.status_code == 200
    assert r.json()["pickup_point_id"] == north

    r = await http.put(
        f"{URL}/employees/{courier}/pickup-point",
        params={"pickup_point_id": north}, headers=admin,
    )
    assert r.status_code == 422

    r = await http.put(
        f"{URL}/employees/{manager}/pickup-point",
        params={"pickup_point_id": 999999}, headers=admin,
    )
    assert r.status_code == 404


# --- games -------------------------------------------------------------


async def test_create_game_refreshes_catalog(http, session, admin):
    assert (await http.get(f"{CATALOG}/games")).json() == []

    r = await http.post(f"{URL}/games", json=GAME, headers=admin)
    assert r.status_code == 201

    titles = [g["title"] for g in (await http.get(f"{CATALOG}/games")).json()]
    assert titles == ["Root"]


async def test_create_game_unknown_category_422(http, session, admin):
    r = await http.post(
        f"{URL}/games", json={**GAME, "category_ids": [999999]}, headers=admin,
    )
    assert r.status_code == 422


async def test_update_game_refreshes_detail(http, session, admin):
    game = await make_game(session, "Dune")
    assert (await http.get(f"{CATALOG}/games/{game}")).json()["title"] == "Dune"

    r = await http.put(
        f"{URL}/games/{game}", json={"title": "Dune: Imperium"}, headers=admin,
    )
    assert r.status_code == 200

    detail = (await http.get(f"{CATALOG}/games/{game}")).json()
    assert detail["title"] == "Dune: Imperium"


async def test_update_game_bad_player_range_422(http, session, admin):
    game = await make_game(session)

    r = await http.put(
        f"{URL}/games/{game}", json={"max_players": 1}, headers=admin,
    )
    assert r.status_code == 422


async def test_set_game_categories(http, session, admin):
    game = await make_game(session)
    cat = await create_category(session, CategoryCreate(name="Coop"))
    params = {"category_id": cat.id}
    assert (await http.get(f"{CATALOG}/games", params=params)).json() == []

    r = await http.put(
        f"{URL}/games/{game}/categories", json=[cat.id], headers=admin,
    )
    assert r.status_code == 200
    assert len((await http.get(f"{CATALOG}/games", params=params)).json()) == 1

    r = await http.put(f"{URL}/games/{game}/categories", json=[], headers=admin)
    assert r.status_code == 200
    assert (await http.get(f"{CATALOG}/games", params=params)).json() == []


async def test_set_categories_unknown_game_404(http, session, admin):
    r = await http.put(f"{URL}/games/999999/categories", json=[], headers=admin)
    assert r.status_code == 404


# --- covers ------------------------------------------------------------


@pytest.fixture
def mock_s3(app):
    s3 = MagicMock()
    app.dependency_overrides[get_storage_client] = lambda: s3
    yield s3
    app.dependency_overrides.pop(get_storage_client, None)


async def test_upload_cover_refreshes_catalog(http, session, admin, mock_s3):
    game = await make_game(session)
    assert (await http.get(f"{CATALOG}/games/{game}")).json()["cover_url"] is None

    r = await http.post(
        f"{URL}/games/{game}/cover",
        files={"file": ("c.png", b"\x89PNG", "image/png")},
        headers=admin,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["cover_key"].startswith(f"covers/{game}/")
    mock_s3.put_object.assert_called_once()

    detail = (await http.get(f"{CATALOG}/games/{game}")).json()
    assert detail["cover_url"] == body["cover_url"]

    r = await http.delete(f"{URL}/games/{game}/cover", headers=admin)
    assert r.status_code == 204
    mock_s3.remove_object.assert_called_once()
    assert (await http.get(f"{CATALOG}/games/{game}")).json()["cover_url"] is None


async def test_upload_cover_wrong_type_422(http, session, admin, mock_s3):
    game = await make_game(session)

    r = await http.post(
        f"{URL}/games/{game}/cover",
        files={"file": ("c.txt", b"hello", "text/plain")},
        headers=admin,
    )
    assert r.status_code == 422
    mock_s3.put_object.assert_not_called()


async def test_upload_cover_requires_file(http, session, admin, mock_s3):
    game = await make_game(session)

    r = await http.post(f"{URL}/games/{game}/cover", headers=admin)
    assert r.status_code == 422


# --- pickup points -----------------------------------------------------


async def test_pickup_point_lifecycle(http, session, admin):
    assert (await http.get(f"{CATALOG}/pickup-points")).json() == []

    r = await http.post(
        f"{URL}/pickup-points",
        json={"name": "Center", "address": "a", "phone": "+7"},
        headers=admin,
    )
    assert r.status_code == 201
    point = r.json()["id"]
    public = (await http.get(f"{CATALOG}/pickup-points")).json()
    assert [p["name"] for p in public] == ["Center"]

    r = await http.put(
        f"{URL}/pickup-points/{point}", json={"address": "b"}, headers=admin,
    )
    assert r.status_code == 200
    public = (await http.get(f"{CATALOG}/pickup-points")).json()
    assert public[0]["address"] == "b"

    r = await http.post(f"{URL}/pickup-points/{point}/deactivate", headers=admin)
    assert r.json()["is_active"] is False
    assert (await http.get(f"{CATALOG}/pickup-points")).json() == []

    r = await http.get(f"{URL}/pickup-points", headers=admin)
    assert [p["id"] for p in r.json()] == [point]

    r = await http.post(f"{URL}/pickup-points/{point}/activate", headers=admin)
    assert r.json()["is_active"] is True
    assert len((await http.get(f"{CATALOG}/pickup-points")).json()) == 1


async def test_pickup_point_duplicate_409(http, session, admin):
    await make_point(session, "Center")

    r = await http.post(
        f"{URL}/pickup-points",
        json={"name": "Center", "address": "a", "phone": "+7"},
        headers=admin,
    )
    assert r.status_code == 409


# --- copies ------------------------------------------------------------


async def test_copy_lifecycle(http, session, admin):
    point = await make_point(session)
    game = await make_game(session)
    body = {"game_id": game, "current_point_id": point, "inventory_number": "INV-1"}

    r = await http.post(f"{URL}/copies", json=body, headers=admin)
    assert r.status_code == 201
    copy_id = r.json()["id"]
    assert r.json()["status"] == "AVAILABLE"

    r = await http.post(f"{URL}/copies", json=body, headers=admin)
    assert r.status_code == 409

    r = await http.put(
        f"{URL}/copies/{copy_id}", json={"inventory_number": "INV-2"},
        headers=admin,
    )
    assert r.status_code == 200
    assert r.json()["inventory_number"] == "INV-2"

    r = await http.get(f"{URL}/copies/{copy_id}", headers=admin)
    assert r.json()["inventory_number"] == "INV-2"


async def test_copy_inactive_point_422(http, session, admin):
    point = await make_point(session)
    game = await make_game(session)
    await http.post(f"{URL}/pickup-points/{point}/deactivate", headers=admin)

    r = await http.post(
        f"{URL}/copies",
        json={"game_id": game, "current_point_id": point, "inventory_number": "INV-1"},
        headers=admin,
    )
    assert r.status_code == 422


async def test_list_copies_filters(http, session, admin):
    point = await make_point(session)
    dune = await make_game(session, "Dune")
    root = await make_game(session, "Root")
    await make_copy(session, dune, point, "INV-1")
    await make_copy(session, dune, point, "INV-2", status="DAMAGED")
    await make_copy(session, root, point, "INV-3")

    r = await http.get(f"{URL}/copies", params={"game_id": dune}, headers=admin)
    assert len(r.json()) == 2

    r = await http.get(
        f"{URL}/copies", params={"game_id": dune, "status": "DAMAGED"},
        headers=admin,
    )
    assert [c["inventory_number"] for c in r.json()] == ["INV-2"]

    r = await http.get(f"{URL}/copies", params={"status": "LOST"}, headers=admin)
    assert r.status_code == 422


async def test_get_copy_404(http, session, admin):
    r = await http.get(f"{URL}/copies/999999", headers=admin)
    assert r.status_code == 404
