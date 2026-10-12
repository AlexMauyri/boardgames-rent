"""Tests for /api/v1/orders/*."""

from datetime import date, timedelta

from app.auth.jwt import create_access_token
from app.db.models import Order
from app.services import deactivate_client
from tests.helpers import make_client, make_copy, make_game, make_point

URL = "/api/v1/orders"


def _headers(client_id: int) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(client_id, 'CLIENT')}"}


def _payload(
    point_id: int,
    game_ids: list[int],
    days: int = 3,
    starts_in: int = 1,
) -> dict:
    start = date.today() + timedelta(days=starts_in)
    return {
        "pickup_point_id": point_id,
        "start_date": start.isoformat(),
        "end_date": (start + timedelta(days=days - 1)).isoformat(),
        "game_ids": game_ids,
    }


async def _force_status(session, order_id: int, status: str) -> None:
    """Directly flip an order's status through the ORM, bypassing the flow."""
    row = await session.get(Order, order_id)
    assert row is not None
    row.status = status
    await session.commit()


# --- create ------------------------------------------------------------


async def test_create_order_without_delivery(http, session):
    point = await make_point(session)
    game = await make_game(session)
    await make_copy(session, game, point, "INV-1")
    client = await make_client(session)

    r = await http.post(URL, json=_payload(point, [game]), headers=_headers(client))

    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "READY_FOR_PICKUP"
    assert body["client_id"] == client
    assert len(body["items"]) == 1


async def test_create_order_with_delivery(http, session):
    source = await make_point(session, "North")
    target = await make_point(session, "Center")
    game = await make_game(session)
    await make_copy(session, game, source, "INV-1")
    client = await make_client(session)

    r = await http.post(URL, json=_payload(target, [game]), headers=_headers(client))

    assert r.status_code == 201
    assert r.json()["status"] == "NEEDS_TRANSFER"


async def test_create_order_unknown_game(http, session):
    point = await make_point(session)
    client = await make_client(session)

    r = await http.post(
        URL, json=_payload(point, [999999]), headers=_headers(client),
    )

    assert r.status_code == 404


async def test_create_order_past_start_date(http, session):
    point = await make_point(session)
    game = await make_game(session)
    await make_copy(session, game, point, "INV-1")
    client = await make_client(session)

    r = await http.post(
        URL,
        json=_payload(point, [game], starts_in=-1),
        headers=_headers(client),
    )

    assert r.status_code == 422


async def test_create_order_no_token(http, session):
    point = await make_point(session)
    r = await http.post(URL, json=_payload(point, [1]))
    assert r.status_code == 401


# --- list --------------------------------------------------------------


async def test_list_returns_only_own_orders(http, session):
    point = await make_point(session)
    game = await make_game(session)
    await make_copy(session, game, point, "INV-1")
    await make_copy(session, game, point, "INV-2")
    alice = await make_client(session, "alice@test.io")
    bob = await make_client(session, "bob@test.io")

    await http.post(URL, json=_payload(point, [game]), headers=_headers(alice))
    await http.post(URL, json=_payload(point, [game]), headers=_headers(bob))

    r = await http.get(URL, headers=_headers(alice))

    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["client_id"] == alice


# --- detail ------------------------------------------------------------


async def test_get_own_order(http, session):
    point = await make_point(session)
    game = await make_game(session)
    await make_copy(session, game, point, "INV-1")
    client = await make_client(session)

    created = await http.post(
        URL, json=_payload(point, [game]), headers=_headers(client),
    )
    order_id = created.json()["id"]

    r = await http.get(f"{URL}/{order_id}", headers=_headers(client))

    assert r.status_code == 200
    assert r.json()["id"] == order_id


async def test_get_foreign_order_returns_404(http, session):
    point = await make_point(session)
    game = await make_game(session)
    await make_copy(session, game, point, "INV-1")
    alice = await make_client(session, "alice@test.io")
    bob = await make_client(session, "bob@test.io")

    created = await http.post(
        URL, json=_payload(point, [game]), headers=_headers(alice),
    )
    order_id = created.json()["id"]

    r = await http.get(f"{URL}/{order_id}", headers=_headers(bob))

    assert r.status_code == 404


# --- cancel ------------------------------------------------------------


async def test_cancel_in_created(http, session):
    point = await make_point(session)
    game = await make_game(session)
    await make_copy(session, game, point, "INV-1")
    client = await make_client(session)

    created = await http.post(
        URL, json=_payload(point, [game]), headers=_headers(client),
    )
    order_id = created.json()["id"]
    await _force_status(session, order_id, "CREATED")

    r = await http.post(f"{URL}/{order_id}/cancel", headers=_headers(client))

    assert r.status_code == 200
    assert r.json()["status"] == "CANCELLED"


async def test_cancel_in_needs_transfer(http, session):
    source = await make_point(session, "North")
    target = await make_point(session, "Center")
    game = await make_game(session)
    await make_copy(session, game, source, "INV-1")
    client = await make_client(session)

    created = await http.post(
        URL, json=_payload(target, [game]), headers=_headers(client),
    )
    order_id = created.json()["id"]

    r = await http.post(f"{URL}/{order_id}/cancel", headers=_headers(client))

    assert r.status_code == 200
    assert r.json()["status"] == "CANCELLED"


async def test_cancel_in_ready_for_pickup(http, session):
    point = await make_point(session)
    game = await make_game(session)
    await make_copy(session, game, point, "INV-1")
    client = await make_client(session)

    created = await http.post(
        URL, json=_payload(point, [game]), headers=_headers(client),
    )
    order_id = created.json()["id"]

    r = await http.post(f"{URL}/{order_id}/cancel", headers=_headers(client))

    assert r.status_code == 200
    assert r.json()["status"] == "CANCELLED"


async def test_cancel_in_transit_conflicts(http, session):
    source = await make_point(session, "North")
    target = await make_point(session, "Center")
    game = await make_game(session)
    await make_copy(session, game, source, "INV-1")
    client = await make_client(session)

    created = await http.post(
        URL, json=_payload(target, [game]), headers=_headers(client),
    )
    order_id = created.json()["id"]
    await _force_status(session, order_id, "IN_TRANSIT")

    r = await http.post(f"{URL}/{order_id}/cancel", headers=_headers(client))

    assert r.status_code == 409


async def test_cancel_active_conflicts(http, session):
    point = await make_point(session)
    game = await make_game(session)
    await make_copy(session, game, point, "INV-1")
    client = await make_client(session)

    created = await http.post(
        URL, json=_payload(point, [game]), headers=_headers(client),
    )
    order_id = created.json()["id"]
    await _force_status(session, order_id, "ACTIVE")

    r = await http.post(f"{URL}/{order_id}/cancel", headers=_headers(client))

    assert r.status_code == 409


async def test_cancel_completed_conflicts(http, session):
    point = await make_point(session)
    game = await make_game(session)
    await make_copy(session, game, point, "INV-1")
    client = await make_client(session)

    created = await http.post(
        URL, json=_payload(point, [game]), headers=_headers(client),
    )
    order_id = created.json()["id"]
    await _force_status(session, order_id, "COMPLETED")

    r = await http.post(f"{URL}/{order_id}/cancel", headers=_headers(client))

    assert r.status_code == 409


async def test_cancel_foreign_order_404(http, session):
    point = await make_point(session)
    game = await make_game(session)
    await make_copy(session, game, point, "INV-1")
    alice = await make_client(session, "alice@test.io")
    bob = await make_client(session, "bob@test.io")

    created = await http.post(
        URL, json=_payload(point, [game]), headers=_headers(alice),
    )
    order_id = created.json()["id"]

    r = await http.post(
        f"{URL}/{order_id}/cancel", headers=_headers(bob),
    )

    assert r.status_code == 404


# --- inactive client ---------------------------------------------------


async def test_inactive_client_rejected(http, session):
    point = await make_point(session)
    client = await make_client(session)
    await deactivate_client(session, client)

    r = await http.get(URL, headers=_headers(client))

    # A deactivated account no longer authenticates: 401, not 403.
    assert r.status_code == 401