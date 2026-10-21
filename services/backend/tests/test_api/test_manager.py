"""Tests for /api/v1/manager/*."""

from decimal import Decimal
from uuid import uuid4

from app.auth.jwt import create_access_token
from app.db.models import GameCopy, Order
from app.services import manager as manager_service
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

URL = "/api/v1/manager"


def _headers(user_id: int, role: str = "MANAGER") -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user_id, role)}"}


def _inv() -> str:
    return f"INV-{uuid4().hex[:8]}"


def _email() -> str:
    return f"c-{uuid4().hex[:6]}@test.io"


async def _fresh(session, model, pk):
    """Re-read a row, bypassing any cached identity from our session."""
    row = await session.get(model, pk)
    await session.refresh(row)
    return row


async def _ready_order(session, point_id: int) -> tuple[int, int]:
    """Create a READY_FOR_PICKUP order at `point_id`. Returns (order, copy)."""
    game = await make_game(session)
    copy_id = await make_copy(session, game, point_id, _inv())
    client_id = await make_client(session, _email())
    detail = await orders_service.create_order(
        session, client_id, order_request(point_id, [game]),
    )
    return detail.id, copy_id


async def _active_order(
    session, point_id: int, manager_id: int,
) -> tuple[int, int, Decimal]:
    """Drive an order to ACTIVE. Returns (order, copy, deposit)."""
    order_id, copy_id = await _ready_order(session, point_id)
    await manager_service.issue_order(session, order_id, manager_id)
    row = await _fresh(session, Order, order_id)
    return order_id, copy_id, row.deposit_paid


# --- list orders -------------------------------------------------------


async def test_list_shows_only_own_point_orders(http, session):
    p1 = await make_point(session, "Center")
    p2 = await make_point(session, "North")
    m1 = await make_manager(session, p1, "m1@test.io")
    m2 = await make_manager(session, p2, "m2@test.io")
    o1, _ = await _ready_order(session, p1)
    o2, _ = await _ready_order(session, p2)

    r1 = await http.get(f"{URL}/orders", headers=_headers(m1))
    assert r1.status_code == 200
    assert [o["id"] for o in r1.json()] == [o1]

    r2 = await http.get(f"{URL}/orders", headers=_headers(m2))
    assert [o["id"] for o in r2.json()] == [o2]


async def test_list_filters_by_status(http, session):
    p = await make_point(session, "Center")
    m = await make_manager(session, p)
    ready_id, _ = await _ready_order(session, p)
    cancelled_id, _ = await _ready_order(session, p)

    row = await session.get(Order, cancelled_id)
    row.status = "CANCELLED"
    await session.commit()

    r = await http.get(
        f"{URL}/orders?status=READY_FOR_PICKUP", headers=_headers(m),
    )
    assert [o["id"] for o in r.json()] == [ready_id]

    r = await http.get(
        f"{URL}/orders?status=CANCELLED", headers=_headers(m),
    )
    assert [o["id"] for o in r.json()] == [cancelled_id]


# --- find order --------------------------------------------------------


async def test_find_own_order(http, session):
    p = await make_point(session, "Center")
    m = await make_manager(session, p)
    order_id, _ = await _ready_order(session, p)

    r = await http.get(f"{URL}/orders/{order_id}", headers=_headers(m))
    assert r.status_code == 200
    assert r.json()["id"] == order_id


async def test_find_foreign_order_404(http, session):
    p1 = await make_point(session, "Center")
    p2 = await make_point(session, "North")
    m2 = await make_manager(session, p2, "m2@test.io")
    order_id, _ = await _ready_order(session, p1)

    r = await http.get(f"{URL}/orders/{order_id}", headers=_headers(m2))
    assert r.status_code == 404


# --- inventory ---------------------------------------------------------


async def test_inventory_only_own_point(http, session):
    p1 = await make_point(session, "Center")
    p2 = await make_point(session, "North")
    m1 = await make_manager(session, p1)

    game = await make_game(session)
    own = await make_copy(session, game, p1, _inv())
    await make_copy(session, game, p2, _inv())

    r = await http.get(f"{URL}/inventory", headers=_headers(m1))
    assert r.status_code == 200
    assert [c["id"] for c in r.json()] == [own]


# --- issue -------------------------------------------------------------


async def test_issue_moves_order_to_active(http, session):
    p = await make_point(session, "Center")
    m = await make_manager(session, p)
    order_id, copy_id = await _ready_order(session, p)

    r = await http.post(
        f"{URL}/orders/{order_id}/issue", headers=_headers(m),
    )
    assert r.status_code == 200
    assert r.json()["status"] == "ACTIVE"

    copy = await _fresh(session, GameCopy, copy_id)
    assert copy.status == "WITH_CLIENT"
    assert copy.current_point_id is None


async def test_issue_wrong_status_conflicts(http, session):
    p = await make_point(session, "Center")
    m = await make_manager(session, p)
    order_id, _ = await _ready_order(session, p)

    row = await session.get(Order, order_id)
    row.status = "CREATED"
    await session.commit()

    r = await http.post(
        f"{URL}/orders/{order_id}/issue", headers=_headers(m),
    )
    assert r.status_code == 409


async def test_issue_box_not_on_shelf_conflicts(http, session):
    p = await make_point(session, "Center")
    m = await make_manager(session, p)
    order_id, copy_id = await _ready_order(session, p)

    # Break the invariant issue_order relies on.
    copy = await session.get(GameCopy, copy_id)
    copy.status = "IN_TRANSIT"
    copy.current_point_id = None
    await session.commit()

    r = await http.post(
        f"{URL}/orders/{order_id}/issue", headers=_headers(m),
    )
    assert r.status_code == 409


# --- return ------------------------------------------------------------


async def test_return_without_damage(http, session):
    p = await make_point(session, "Center")
    m = await make_manager(session, p)
    order_id, copy_id, deposit = await _active_order(session, p, m)

    r = await http.post(
        f"{URL}/orders/{order_id}/return",
        headers=_headers(m),
        json={"damages": []},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["order"]["status"] == "COMPLETED"
    assert body["damage_reports"] == []
    assert Decimal(body["deposit_refund"]) == deposit

    copy = await _fresh(session, GameCopy, copy_id)
    assert copy.status == "AVAILABLE"
    assert copy.current_point_id == p


async def test_return_with_damage(http, session):
    p = await make_point(session, "Center")
    m = await make_manager(session, p)
    order_id, copy_id, deposit = await _active_order(session, p, m)

    r = await http.post(
        f"{URL}/orders/{order_id}/return",
        headers=_headers(m),
        json={
            "damages": [
                {
                    "game_copy_id": copy_id,
                    "description": "torn corner",
                    "deposit_withheld": "300.00",
                }
            ]
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["order"]["status"] == "COMPLETED"
    assert Decimal(body["deposit_refund"]) == deposit - Decimal("300.00")
    assert len(body["damage_reports"]) == 1
    assert body["damage_reports"][0]["game_copy_id"] == copy_id

    copy = await _fresh(session, GameCopy, copy_id)
    assert copy.status == "DAMAGED"


async def test_return_withheld_exceeds_deposit(http, session):
    p = await make_point(session, "Center")
    m = await make_manager(session, p)
    order_id, copy_id, deposit = await _active_order(session, p, m)

    r = await http.post(
        f"{URL}/orders/{order_id}/return",
        headers=_headers(m),
        json={
            "damages": [
                {
                    "game_copy_id": copy_id,
                    "description": "gone",
                    "deposit_withheld": str(deposit + Decimal("1000")),
                }
            ]
        },
    )
    assert r.status_code == 422


async def test_return_box_not_in_order(http, session):
    p = await make_point(session, "Center")
    m = await make_manager(session, p)
    order_id, _, _ = await _active_order(session, p, m)

    other_game = await make_game(session, "Other")
    other_copy = await make_copy(session, other_game, p, _inv())

    r = await http.post(
        f"{URL}/orders/{order_id}/return",
        headers=_headers(m),
        json={
            "damages": [
                {
                    "game_copy_id": other_copy,
                    "description": "x",
                    "deposit_withheld": "0",
                }
            ]
        },
    )
    assert r.status_code == 422


# --- report_damage (planned inspection) --------------------------------


async def test_report_damage_planned(http, session):
    p = await make_point(session, "Center")
    m = await make_manager(session, p)
    game = await make_game(session)
    copy_id = await make_copy(session, game, p, _inv())

    r = await http.post(
        f"{URL}/damage-reports",
        headers=_headers(m),
        json={
            "game_copy_id": copy_id,
            "description": "missing die",
            "deposit_withheld": "0",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["game_copy_id"] == copy_id
    assert body["order_id"] is None
    assert Decimal(body["deposit_withheld"]) == Decimal("0")

    copy = await _fresh(session, GameCopy, copy_id)
    assert copy.status == "DAMAGED"


async def test_report_damage_with_order_rejected(http, session):
    p = await make_point(session, "Center")
    m = await make_manager(session, p)
    game = await make_game(session)
    copy_id = await make_copy(session, game, p, _inv())

    r = await http.post(
        f"{URL}/damage-reports",
        headers=_headers(m),
        json={
            "game_copy_id": copy_id,
            "order_id": 1,
            "description": "x",
            "deposit_withheld": "0",
        },
    )
    assert r.status_code == 422


async def test_report_damage_with_deposit_rejected(http, session):
    p = await make_point(session, "Center")
    m = await make_manager(session, p)
    game = await make_game(session)
    copy_id = await make_copy(session, game, p, _inv())

    r = await http.post(
        f"{URL}/damage-reports",
        headers=_headers(m),
        json={
            "game_copy_id": copy_id,
            "description": "x",
            "deposit_withheld": "10.00",
        },
    )
    assert r.status_code == 422


async def test_report_damage_foreign_point_forbidden(http, session):
    p1 = await make_point(session, "Center")
    p2 = await make_point(session, "North")
    m1 = await make_manager(session, p1)
    game = await make_game(session)
    copy_id = await make_copy(session, game, p2, _inv())

    r = await http.post(
        f"{URL}/damage-reports",
        headers=_headers(m1),
        json={
            "game_copy_id": copy_id,
            "description": "x",
            "deposit_withheld": "0",
        },
    )
    assert r.status_code == 403


# --- role gating -------------------------------------------------------


async def test_client_gets_403(http, session):
    client_id = await make_client(session, _email())
    r = await http.get(f"{URL}/orders", headers=_headers(client_id, "CLIENT"))
    assert r.status_code == 403


async def test_courier_gets_403(http, session):
    c = await make_courier(session)
    r = await http.get(f"{URL}/orders", headers=_headers(c, "COURIER"))
    assert r.status_code == 403