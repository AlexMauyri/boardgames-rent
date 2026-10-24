"""Tests for /api/v1/courier/*."""

from app.auth.jwt import create_access_token
from app.crud import delivery as delivery_crud
from app.db.models import GameCopy, Order
from app.services import orders as orders_service
from tests.helpers import (
    make_client,
    make_copy,
    make_courier,
    make_game,
    make_manager,
    make_point,
    order_request,
)

URL = "/api/v1/courier/deliveries"


def _headers(user_id: int, role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user_id, role)}"}


async def _make_transfer(session) -> dict:
    """Box at North, order to collect at Center: creates a delivery."""
    source = await make_point(session, "North")
    target = await make_point(session, "Center")
    game = await make_game(session)
    copy = await make_copy(session, game, source, "INV-1")
    client = await make_client(session)

    detail = await orders_service.create_order(
        session, client, order_request(target, [game]),
    )
    delivery = await delivery_crud.get_by_order(session, detail.id)
    assert delivery is not None

    return {
        "delivery_id": delivery.id,
        "order_id": detail.id,
        "copy_id": copy,
        "source": source,
        "target": target,
    }


async def _reload(session, model, pk):
    """Force a fresh read of a row, bypassing any cached identity."""
    row = await session.get(model, pk)
    await session.refresh(row)
    return row


# --- open list ---------------------------------------------------------


async def test_open_shows_only_unassigned_created(http, session):
    ctx = await _make_transfer(session)
    c1 = await make_courier(session, "c1@test.io")
    c2 = await make_courier(session, "c2@test.io")

    r1 = await http.get(f"{URL}/open", headers=_headers(c1, "COURIER"))
    assert r1.status_code == 200
    assert [d["id"] for d in r1.json()] == [ctx["delivery_id"]]

    await http.post(
        f"{URL}/{ctx['delivery_id']}/accept",
        headers=_headers(c1, "COURIER"),
    )

    r2 = await http.get(f"{URL}/open", headers=_headers(c2, "COURIER"))
    assert r2.status_code == 200
    assert r2.json() == []


# --- own list ----------------------------------------------------------


async def test_active_only_toggle(http, session):
    ctx = await _make_transfer(session)
    courier = await make_courier(session)
    h = _headers(courier, "COURIER")
    await http.post(f"{URL}/{ctx['delivery_id']}/accept", headers=h)

    active = await http.get(URL, headers=h)
    assert [d["id"] for d in active.json()] == [ctx["delivery_id"]]

    all_rows = await http.get(f"{URL}?active_only=false", headers=h)
    assert [d["id"] for d in all_rows.json()] == [ctx["delivery_id"]]

    await http.post(f"{URL}/{ctx['delivery_id']}/start", headers=h)
    await http.post(f"{URL}/{ctx['delivery_id']}/complete", headers=h)

    active2 = await http.get(URL, headers=h)
    assert active2.json() == []

    all2 = await http.get(f"{URL}?active_only=false", headers=h)
    assert [d["id"] for d in all2.json()] == [ctx["delivery_id"]]


# --- accept ------------------------------------------------------------


async def test_accept_sets_courier_and_status(http, session):
    ctx = await _make_transfer(session)
    courier = await make_courier(session)

    r = await http.post(
        f"{URL}/{ctx['delivery_id']}/accept",
        headers=_headers(courier, "COURIER"),
    )

    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ACCEPTED"
    assert body["courier_id"] == courier


async def test_accept_twice_conflicts(http, session):
    ctx = await _make_transfer(session)
    c1 = await make_courier(session, "c1@test.io")
    c2 = await make_courier(session, "c2@test.io")

    r1 = await http.post(
        f"{URL}/{ctx['delivery_id']}/accept",
        headers=_headers(c1, "COURIER"),
    )
    assert r1.status_code == 200

    r2 = await http.post(
        f"{URL}/{ctx['delivery_id']}/accept",
        headers=_headers(c2, "COURIER"),
    )
    assert r2.status_code == 409


# --- start -------------------------------------------------------------


async def test_start_moves_boxes_and_order(http, session):
    ctx = await _make_transfer(session)
    courier = await make_courier(session)
    h = _headers(courier, "COURIER")
    await http.post(f"{URL}/{ctx['delivery_id']}/accept", headers=h)

    r = await http.post(f"{URL}/{ctx['delivery_id']}/start", headers=h)
    assert r.status_code == 200
    assert r.json()["status"] == "IN_TRANSIT"

    copy = await _reload(session, GameCopy, ctx["copy_id"])
    assert copy.status == "IN_TRANSIT"
    assert copy.current_point_id is None

    order = await _reload(session, Order, ctx["order_id"])
    assert order.status == "IN_TRANSIT"


async def test_start_without_boxes_at_source_conflicts(http, session):
    ctx = await _make_transfer(session)
    courier = await make_courier(session)
    h = _headers(courier, "COURIER")
    await http.post(f"{URL}/{ctx['delivery_id']}/accept", headers=h)

    # Move the box away from the source point, breaking the invariant
    # start_delivery relies on.
    copy = await _reload(session, GameCopy, ctx["copy_id"])
    copy.status = "WITH_CLIENT"
    copy.current_point_id = None
    await session.commit()

    r = await http.post(f"{URL}/{ctx['delivery_id']}/start", headers=h)
    assert r.status_code == 409


# --- complete ----------------------------------------------------------


async def test_complete_moves_boxes_to_destination(http, session):
    ctx = await _make_transfer(session)
    courier = await make_courier(session)
    h = _headers(courier, "COURIER")
    await http.post(f"{URL}/{ctx['delivery_id']}/accept", headers=h)
    await http.post(f"{URL}/{ctx['delivery_id']}/start", headers=h)

    r = await http.post(f"{URL}/{ctx['delivery_id']}/complete", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "DELIVERED"
    assert body["delivered_at"] is not None

    copy = await _reload(session, GameCopy, ctx["copy_id"])
    assert copy.status == "AVAILABLE"
    assert copy.current_point_id == ctx["target"]

    order = await _reload(session, Order, ctx["order_id"])
    assert order.status == "READY_FOR_PICKUP"


async def test_complete_before_start_conflicts(http, session):
    ctx = await _make_transfer(session)
    courier = await make_courier(session)
    h = _headers(courier, "COURIER")
    await http.post(f"{URL}/{ctx['delivery_id']}/accept", headers=h)

    r = await http.post(f"{URL}/{ctx['delivery_id']}/complete", headers=h)
    assert r.status_code == 409


# --- access control ----------------------------------------------------


async def test_non_courier_gets_403(http, session):
    client = await make_client(session)
    r = await http.get(f"{URL}/open", headers=_headers(client, "CLIENT"))
    assert r.status_code == 403


async def test_manager_gets_403(http, session):
    point = await make_point(session, "Center")
    manager = await make_manager(session, point)
    r = await http.get(f"{URL}/open", headers=_headers(manager, "MANAGER"))
    assert r.status_code == 403


async def test_foreign_courier_cannot_start(http, session):
    ctx = await _make_transfer(session)
    c1 = await make_courier(session, "c1@test.io")
    c2 = await make_courier(session, "c2@test.io")

    await http.post(
        f"{URL}/{ctx['delivery_id']}/accept",
        headers=_headers(c1, "COURIER"),
    )

    r = await http.post(
        f"{URL}/{ctx['delivery_id']}/start",
        headers=_headers(c2, "COURIER"),
    )
    assert r.status_code == 403