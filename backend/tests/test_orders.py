"""Tests for placing, viewing and cancelling orders."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.crud import delivery as delivery_crud
from app.crud import game_copy
from app.schemas import OrderCreate
from app.services import (
    ForbiddenError,
    InvalidTransitionError,
    NotAvailableError,
    NotFoundError,
    accept_delivery,
    cancel_order,
    create_order,
    deactivate_client,
    deactivate_pickup_point,
    get_order,
    list_client_orders,
    start_delivery,
)
from tests.helpers import (
    make_client,
    make_copy,
    make_courier,
    make_game,
    make_point,
    order_request,
)


async def test_box_at_pickup_point_gives_ready_order_without_delivery(session):
    point = await make_point(session)
    client_id = await make_client(session)
    game = await make_game(session, daily="300", deposit="1000")
    copy_id = await make_copy(session, game, point, "INV-1")

    order = await create_order(
        session, client_id, order_request(point, [game], days=3),
    )

    assert order.status == "READY_FOR_PICKUP"
    assert order.client_id == client_id
    assert order.total_price == Decimal("900.00")
    assert order.deposit_paid == Decimal("1000.00")
    assert [(i.game_copy_id, i.price_at_rental) for i in order.items] == [
        (copy_id, Decimal("300.00")),
    ]
    assert await delivery_crud.get_by_order(session, order.id) is None


async def test_box_at_another_point_creates_delivery(session):
    here = await make_point(session, "Center")
    north = await make_point(session, "North")
    client_id = await make_client(session)
    game = await make_game(session)
    await make_copy(session, game, north, "INV-1")

    order = await create_order(session, client_id, order_request(here, [game]))

    assert order.status == "NEEDS_TRANSFER"
    task = await delivery_crud.get_by_order(session, order.id)
    assert task.from_point_id == north
    assert task.to_point_id == here
    assert task.status == "CREATED"
    assert task.courier_id is None


async def test_order_for_two_games_sums_prices_and_deposits(session):
    point = await make_point(session)
    client_id = await make_client(session)
    dune = await make_game(session, "Dune", daily="300", deposit="1000")
    chess = await make_game(session, "Chess", daily="50", deposit="200")
    await make_copy(session, dune, point, "INV-1")
    await make_copy(session, chess, point, "INV-2")

    order = await create_order(
        session, client_id, order_request(point, [dune, chess], days=2),
    )

    assert order.total_price == Decimal("700.00")
    assert order.deposit_paid == Decimal("1200.00")
    assert len(order.items) == 2


async def test_same_game_twice_needs_two_boxes(session):
    point = await make_point(session)
    client_id = await make_client(session)
    game = await make_game(session)
    await make_copy(session, game, point, "INV-1")

    with pytest.raises(NotAvailableError):
        await create_order(session, client_id, order_request(point, [game, game]))

    await make_copy(session, game, point, "INV-2")
    order = await create_order(
        session, client_id, order_request(point, [game, game]),
    )
    assert len(order.items) == 2


async def test_booked_box_is_not_offered_to_a_second_client(session):
    point = await make_point(session)
    first = await make_client(session, "first@test.io")
    second = await make_client(session, "second@test.io")
    game = await make_game(session)
    await make_copy(session, game, point, "INV-1")

    await create_order(session, first, order_request(point, [game]))

    with pytest.raises(NotAvailableError) as exc:
        await create_order(session, second, order_request(point, [game]))
    assert exc.value.game_ids == [game]


async def test_damaged_box_is_not_offered(session):
    point = await make_point(session)
    client_id = await make_client(session)
    game = await make_game(session)
    await make_copy(session, game, point, "INV-1", status="DAMAGED")

    with pytest.raises(NotAvailableError):
        await create_order(session, client_id, order_request(point, [game]))


async def test_box_with_a_client_is_not_offered(session):
    point = await make_point(session)
    client_id = await make_client(session)
    game = await make_game(session)
    await make_copy(session, game, None, "INV-1", status="WITH_CLIENT")

    with pytest.raises(NotAvailableError):
        await create_order(session, client_id, order_request(point, [game]))


async def test_start_date_in_the_past_rejected(session):
    point = await make_point(session)
    client_id = await make_client(session)
    game = await make_game(session)
    await make_copy(session, game, point, "INV-1")
    yesterday = date.today() - timedelta(days=1)

    with pytest.raises(ValueError):
        await create_order(session, client_id, OrderCreate(
            pickup_point_id=point, start_date=yesterday, end_date=yesterday,
            game_ids=[game],
        ))


async def test_order_starting_today_is_allowed(session):
    point = await make_point(session)
    client_id = await make_client(session)
    game = await make_game(session)
    await make_copy(session, game, point, "INV-1")

    order = await create_order(
        session, client_id, order_request(point, [game], days=1, starts_in=0),
    )
    assert order.status == "READY_FOR_PICKUP"


async def test_unknown_game_rejected(session):
    point = await make_point(session)
    client_id = await make_client(session)

    with pytest.raises(NotFoundError):
        await create_order(session, client_id, order_request(point, [999999]))


async def test_unknown_pickup_point_rejected(session):
    client_id = await make_client(session)
    game = await make_game(session)

    with pytest.raises(NotFoundError):
        await create_order(session, client_id, order_request(999999, [game]))


async def test_inactive_pickup_point_rejected(session):
    point = await make_point(session)
    client_id = await make_client(session)
    game = await make_game(session)
    await make_copy(session, game, point, "INV-1")
    await deactivate_pickup_point(session, point)

    with pytest.raises(ValueError):
        await create_order(session, client_id, order_request(point, [game]))


async def test_unknown_client_rejected(session):
    point = await make_point(session)
    game = await make_game(session)

    with pytest.raises(NotFoundError):
        await create_order(session, 999999, order_request(point, [game]))


async def test_disabled_client_rejected(session):
    point = await make_point(session)
    client_id = await make_client(session)
    game = await make_game(session)
    await make_copy(session, game, point, "INV-1")
    await deactivate_client(session, client_id)

    with pytest.raises(ForbiddenError):
        await create_order(session, client_id, order_request(point, [game]))


async def test_failed_order_leaves_stock_untouched(session):
    point = await make_point(session)
    client_id = await make_client(session)
    game = await make_game(session)
    copy_id = await make_copy(session, game, point, "INV-1")

    with pytest.raises(NotAvailableError):
        await create_order(session, client_id, order_request(point, [game, game]))

    assert await list_client_orders(session, client_id) == []
    copy = await game_copy.get(session, copy_id)
    assert copy.status == "AVAILABLE"


async def test_get_order_returns_lines(session):
    point = await make_point(session)
    client_id = await make_client(session)
    game = await make_game(session)
    await make_copy(session, game, point, "INV-1")
    placed = await create_order(session, client_id, order_request(point, [game]))

    fetched = await get_order(session, placed.id, client_id)
    assert fetched.id == placed.id
    assert len(fetched.items) == 1


async def test_get_order_of_another_client_is_not_found(session):
    point = await make_point(session)
    owner = await make_client(session, "owner@test.io")
    other = await make_client(session, "other@test.io")
    game = await make_game(session)
    await make_copy(session, game, point, "INV-1")
    placed = await create_order(session, owner, order_request(point, [game]))

    with pytest.raises(NotFoundError):
        await get_order(session, placed.id, other)


async def test_get_order_without_owner_filter_for_staff(session):
    point = await make_point(session)
    owner = await make_client(session)
    game = await make_game(session)
    await make_copy(session, game, point, "INV-1")
    placed = await create_order(session, owner, order_request(point, [game]))

    assert (await get_order(session, placed.id)).id == placed.id


async def test_list_client_orders_returns_only_own_newest_first(session):
    point = await make_point(session)
    me = await make_client(session, "me@test.io")
    other = await make_client(session, "other@test.io")
    game = await make_game(session)
    await make_copy(session, game, point, "INV-1")
    await make_copy(session, game, point, "INV-2")
    await make_copy(session, game, point, "INV-3")
    first = await create_order(session, me, order_request(point, [game]))
    second = await create_order(session, me, order_request(point, [game]))
    await create_order(session, other, order_request(point, [game]))

    rows = await list_client_orders(session, me)
    assert [r.id for r in rows] == [second.id, first.id]


async def test_cancel_releases_the_box(session):
    point = await make_point(session)
    first = await make_client(session, "first@test.io")
    second = await make_client(session, "second@test.io")
    game = await make_game(session)
    await make_copy(session, game, point, "INV-1")
    placed = await create_order(session, first, order_request(point, [game]))

    cancelled = await cancel_order(session, placed.id, first)
    assert cancelled.status == "CANCELLED"

    again = await create_order(session, second, order_request(point, [game]))
    assert again.status == "READY_FOR_PICKUP"


async def test_cancel_before_pickup_deletes_the_delivery(session):
    here = await make_point(session, "Center")
    north = await make_point(session, "North")
    client_id = await make_client(session)
    game = await make_game(session)
    await make_copy(session, game, north, "INV-1")
    placed = await create_order(session, client_id, order_request(here, [game]))

    await cancel_order(session, placed.id, client_id)

    assert await delivery_crud.get_by_order(session, placed.id) is None


async def test_cancel_after_courier_accepted_still_deletes_delivery(session):
    here = await make_point(session, "Center")
    north = await make_point(session, "North")
    client_id = await make_client(session)
    courier = await make_courier(session)
    game = await make_game(session)
    await make_copy(session, game, north, "INV-1")
    placed = await create_order(session, client_id, order_request(here, [game]))
    task = await delivery_crud.get_by_order(session, placed.id)
    await accept_delivery(session, task.id, courier)

    await cancel_order(session, placed.id, client_id)

    assert await delivery_crud.get_by_order(session, placed.id) is None


async def test_cancel_in_transit_refused(session):
    here = await make_point(session, "Center")
    north = await make_point(session, "North")
    client_id = await make_client(session)
    courier = await make_courier(session)
    game = await make_game(session)
    await make_copy(session, game, north, "INV-1")
    placed = await create_order(session, client_id, order_request(here, [game]))
    task = await delivery_crud.get_by_order(session, placed.id)
    await accept_delivery(session, task.id, courier)
    await start_delivery(session, task.id, courier)

    with pytest.raises(InvalidTransitionError):
        await cancel_order(session, placed.id, client_id)


async def test_cancel_twice_refused(session):
    point = await make_point(session)
    client_id = await make_client(session)
    game = await make_game(session)
    await make_copy(session, game, point, "INV-1")
    placed = await create_order(session, client_id, order_request(point, [game]))
    await cancel_order(session, placed.id, client_id)

    with pytest.raises(InvalidTransitionError):
        await cancel_order(session, placed.id, client_id)


async def test_cancel_someone_elses_order_is_not_found(session):
    point = await make_point(session)
    owner = await make_client(session, "owner@test.io")
    other = await make_client(session, "other@test.io")
    game = await make_game(session)
    await make_copy(session, game, point, "INV-1")
    placed = await create_order(session, owner, order_request(point, [game]))

    with pytest.raises(NotFoundError):
        await cancel_order(session, placed.id, other)
