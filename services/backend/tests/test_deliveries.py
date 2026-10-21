"""Tests for the courier flow: accept, pick up, hand over."""

import pytest

from app.crud import delivery as delivery_crud
from app.crud import game_copy
from app.services import (
    ForbiddenError,
    InvalidTransitionError,
    NotFoundError,
    accept_delivery,
    complete_delivery,
    create_order,
    get_order,
    list_courier_deliveries,
    list_open_deliveries,
    start_delivery,
)
from tests.helpers import (
    make_client,
    make_copy,
    make_courier,
    make_employee,
    make_game,
    make_point,
    order_request,
)


async def _transfer_order(session):
    """One order whose only box must travel from North to Center."""
    here = await make_point(session, "Center")
    north = await make_point(session, "North")
    client_id = await make_client(session)
    courier = await make_courier(session)
    game = await make_game(session)
    copy_id = await make_copy(session, game, north, "INV-1")
    order = await create_order(session, client_id, order_request(here, [game]))
    task = await delivery_crud.get_by_order(session, order.id)
    return dict(
        here=here, north=north, courier=courier, copy_id=copy_id,
        order_id=order.id, delivery_id=task.id,
    )


async def test_new_delivery_is_listed_as_open(session):
    w = await _transfer_order(session)

    rows = await list_open_deliveries(session)

    assert [r.id for r in rows] == [w["delivery_id"]]
    assert rows[0].status == "CREATED"


async def test_full_delivery_lifecycle(session):
    w = await _transfer_order(session)

    accepted = await accept_delivery(session, w["delivery_id"], w["courier"])
    assert accepted.status == "ACCEPTED"
    assert accepted.courier_id == w["courier"]
    assert await list_open_deliveries(session) == []
    mine = await list_courier_deliveries(session, w["courier"])
    assert [d.id for d in mine] == [w["delivery_id"]]
    assert (await get_order(session, w["order_id"])).status == "NEEDS_TRANSFER"

    started = await start_delivery(session, w["delivery_id"], w["courier"])
    assert started.status == "IN_TRANSIT"
    copy = await game_copy.get(session, w["copy_id"])
    assert (copy.status, copy.current_point_id) == ("IN_TRANSIT", None)
    assert (await get_order(session, w["order_id"])).status == "IN_TRANSIT"

    done = await complete_delivery(session, w["delivery_id"], w["courier"])
    assert done.status == "DELIVERED"
    assert done.delivered_at is not None
    copy = await game_copy.get(session, w["copy_id"])
    assert (copy.status, copy.current_point_id) == ("AVAILABLE", w["here"])
    assert (await get_order(session, w["order_id"])).status == "READY_FOR_PICKUP"
    assert await list_courier_deliveries(session, w["courier"]) == []


async def test_finished_delivery_stays_in_courier_history(session):
    w = await _transfer_order(session)
    for step in (accept_delivery, start_delivery, complete_delivery):
        await step(session, w["delivery_id"], w["courier"])

    history = await list_courier_deliveries(
        session, w["courier"], active_only=False,
    )
    assert [d.status for d in history] == ["DELIVERED"]


async def test_only_travelling_boxes_leave_their_shelf(session):
    here = await make_point(session, "Center")
    north = await make_point(session, "North")
    client_id = await make_client(session)
    courier = await make_courier(session)
    local_game = await make_game(session, "Local")
    remote_game = await make_game(session, "Remote")
    local_copy = await make_copy(session, local_game, here, "INV-1")
    remote_copy = await make_copy(session, remote_game, north, "INV-2")
    order = await create_order(
        session, client_id, order_request(here, [local_game, remote_game]),
    )
    task = await delivery_crud.get_by_order(session, order.id)

    await accept_delivery(session, task.id, courier)
    await start_delivery(session, task.id, courier)
    local = await game_copy.get(session, local_copy)
    remote = await game_copy.get(session, remote_copy)
    assert (local.status, local.current_point_id) == ("AVAILABLE", here)
    assert remote.status == "IN_TRANSIT"

    await complete_delivery(session, task.id, courier)
    remote = await game_copy.get(session, remote_copy)
    assert (remote.status, remote.current_point_id) == ("AVAILABLE", here)
    assert (await get_order(session, order.id)).status == "READY_FOR_PICKUP"


async def test_accepting_twice_refused(session):
    w = await _transfer_order(session)
    await accept_delivery(session, w["delivery_id"], w["courier"])

    with pytest.raises(InvalidTransitionError):
        await accept_delivery(session, w["delivery_id"], w["courier"])


async def test_second_courier_cannot_take_an_accepted_task(session):
    w = await _transfer_order(session)
    other = await make_courier(session, "other@test.io")
    await accept_delivery(session, w["delivery_id"], w["courier"])

    with pytest.raises(InvalidTransitionError):
        await accept_delivery(session, w["delivery_id"], other)


async def test_non_courier_cannot_accept(session):
    w = await _transfer_order(session)
    admin = await make_employee(session, "ADMIN", "admin@test.io")

    with pytest.raises(ForbiddenError):
        await accept_delivery(session, w["delivery_id"], admin)


async def test_unknown_courier_or_delivery_not_found(session):
    w = await _transfer_order(session)

    with pytest.raises(NotFoundError):
        await accept_delivery(session, w["delivery_id"], 999999)
    with pytest.raises(NotFoundError):
        await accept_delivery(session, 999999, w["courier"])


async def test_other_courier_cannot_start_or_complete(session):
    w = await _transfer_order(session)
    other = await make_courier(session, "other@test.io")
    await accept_delivery(session, w["delivery_id"], w["courier"])

    with pytest.raises(ForbiddenError):
        await start_delivery(session, w["delivery_id"], other)
    await start_delivery(session, w["delivery_id"], w["courier"])
    with pytest.raises(ForbiddenError):
        await complete_delivery(session, w["delivery_id"], other)


async def test_start_before_accept_refused(session):
    w = await _transfer_order(session)

    with pytest.raises(ForbiddenError):
        await start_delivery(session, w["delivery_id"], w["courier"])


async def test_complete_before_start_refused(session):
    w = await _transfer_order(session)
    await accept_delivery(session, w["delivery_id"], w["courier"])

    with pytest.raises(InvalidTransitionError):
        await complete_delivery(session, w["delivery_id"], w["courier"])


async def test_start_twice_refused(session):
    w = await _transfer_order(session)
    await accept_delivery(session, w["delivery_id"], w["courier"])
    await start_delivery(session, w["delivery_id"], w["courier"])

    with pytest.raises(InvalidTransitionError):
        await start_delivery(session, w["delivery_id"], w["courier"])


async def test_cancelled_order_disappears_from_open_list(session):
    from app.services import cancel_order

    w = await _transfer_order(session)
    order = await get_order(session, w["order_id"])

    await cancel_order(session, w["order_id"], order.client_id)

    assert await list_open_deliveries(session) == []
