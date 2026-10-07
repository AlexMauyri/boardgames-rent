"""Tests for the manager flow: view the point, issue, accept return."""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.crud import delivery as delivery_crud
from app.crud import employee as employee_crud
from app.crud import game_copy
from app.schemas import OrderReturnCreate, ReturnDamage
from app.services import (
    ForbiddenError,
    InvalidTransitionError,
    NotAvailableError,
    NotFoundError,
    accept_delivery,
    accept_return,
    complete_delivery,
    create_order,
    find_point_order,
    get_order,
    issue_order,
    list_point_inventory,
    list_point_orders,
    start_delivery,
)
from tests.helpers import (
    make_client,
    make_copy,
    make_courier,
    make_game,
    make_manager,
    make_point,
    order_request,
)


async def _ready_order(session, deposit="1000"):
    """One READY_FOR_PICKUP order, its box on the shelf of its own point."""
    point = await make_point(session, "Center")
    manager = await make_manager(session, point)
    client_id = await make_client(session)
    game = await make_game(session, deposit=deposit)
    copy_id = await make_copy(session, game, point, "INV-1")
    order = await create_order(session, client_id, order_request(point, [game]))
    return dict(
        point=point, manager=manager, client=client_id, game=game,
        copy_id=copy_id, order_id=order.id,
    )


async def _active_order(session, deposit="1000"):
    w = await _ready_order(session, deposit)
    await issue_order(session, w["order_id"], w["manager"])
    return w


def _return(*damages: ReturnDamage) -> OrderReturnCreate:
    return OrderReturnCreate(damages=list(damages))


async def test_manager_sees_only_orders_of_own_point(session):
    w = await _ready_order(session)
    other_point = await make_point(session, "North")
    other_manager = await make_manager(session, other_point, "other@test.io")

    mine = await list_point_orders(session, w["manager"])
    theirs = await list_point_orders(session, other_manager)

    assert [o.id for o in mine] == [w["order_id"]]
    assert theirs == []


async def test_list_point_orders_filters_by_status(session):
    w = await _ready_order(session)

    ready = await list_point_orders(session, w["manager"], status="READY_FOR_PICKUP")
    active = await list_point_orders(session, w["manager"], status="ACTIVE")

    assert len(ready) == 1
    assert active == []


async def test_find_point_order_by_number(session):
    w = await _ready_order(session)

    found = await find_point_order(session, w["manager"], w["order_id"])

    assert found.status == "READY_FOR_PICKUP"
    assert len(found.items) == 1


async def test_find_order_of_another_point_is_not_found(session):
    w = await _ready_order(session)
    other_point = await make_point(session, "North")
    other_manager = await make_manager(session, other_point, "other@test.io")

    with pytest.raises(NotFoundError):
        await find_point_order(session, other_manager, w["order_id"])


async def test_inventory_lists_boxes_of_own_point_only(session):
    w = await _ready_order(session)
    other_point = await make_point(session, "North")
    await make_copy(session, w["game"], other_point, "INV-2")

    rows = await list_point_inventory(session, w["manager"])

    assert [r.id for r in rows] == [w["copy_id"]]


async def test_inventory_drops_boxes_that_left_with_the_client(session):
    w = await _ready_order(session)
    await issue_order(session, w["order_id"], w["manager"])

    assert await list_point_inventory(session, w["manager"]) == []


async def test_non_manager_is_refused(session):
    w = await _ready_order(session)
    courier = await make_courier(session)

    with pytest.raises(ForbiddenError):
        await list_point_orders(session, courier)
    with pytest.raises(ForbiddenError):
        await issue_order(session, w["order_id"], courier)


async def test_unknown_employee_not_found(session):
    with pytest.raises(NotFoundError):
        await list_point_orders(session, 999999)


async def test_deactivated_manager_is_refused(session):
    w = await _ready_order(session)
    await employee_crud.deactivate(session, id=w["manager"])
    await session.commit()

    with pytest.raises(ForbiddenError):
        await issue_order(session, w["order_id"], w["manager"])


async def test_issue_hands_boxes_to_the_client(session):
    w = await _ready_order(session)

    issued = await issue_order(session, w["order_id"], w["manager"])

    assert issued.status == "ACTIVE"
    copy = await game_copy.get(session, w["copy_id"])
    assert (copy.status, copy.current_point_id) == ("WITH_CLIENT", None)


async def test_issue_by_manager_of_another_point_is_not_found(session):
    w = await _ready_order(session)
    other_point = await make_point(session, "North")
    other_manager = await make_manager(session, other_point, "other@test.io")

    with pytest.raises(NotFoundError):
        await issue_order(session, w["order_id"], other_manager)


async def test_issue_twice_refused(session):
    w = await _ready_order(session)
    await issue_order(session, w["order_id"], w["manager"])

    with pytest.raises(InvalidTransitionError):
        await issue_order(session, w["order_id"], w["manager"])


async def test_issue_refused_while_box_is_still_travelling(session):
    here = await make_point(session, "Center")
    north = await make_point(session, "North")
    manager = await make_manager(session, here)
    client_id = await make_client(session)
    game = await make_game(session)
    await make_copy(session, game, north, "INV-1")
    order = await create_order(session, client_id, order_request(here, [game]))

    with pytest.raises(InvalidTransitionError):
        await issue_order(session, order.id, manager)


async def test_box_delivered_by_courier_can_be_issued(session):
    here = await make_point(session, "Center")
    north = await make_point(session, "North")
    manager = await make_manager(session, here)
    courier = await make_courier(session)
    client_id = await make_client(session)
    game = await make_game(session)
    await make_copy(session, game, north, "INV-1")
    order = await create_order(session, client_id, order_request(here, [game]))
    task = await delivery_crud.get_by_order(session, order.id)
    for step in (accept_delivery, start_delivery, complete_delivery):
        await step(session, task.id, courier)

    issued = await issue_order(session, order.id, manager)

    assert issued.status == "ACTIVE"


async def test_return_without_damage_completes_the_rental(session):
    w = await _active_order(session)

    result = await accept_return(session, w["order_id"], w["manager"], _return())

    assert result.order.status == "COMPLETED"
    assert result.damage_reports == []
    assert result.deposit_refund == Decimal("1000.00")
    copy = await game_copy.get(session, w["copy_id"])
    assert (copy.status, copy.current_point_id) == ("AVAILABLE", w["point"])


async def test_returned_box_can_be_ordered_again(session):
    w = await _active_order(session)
    await accept_return(session, w["order_id"], w["manager"], _return())
    second = await make_client(session, "second@test.io")

    again = await create_order(
        session, second, order_request(w["point"], [w["game"]]),
    )

    assert again.status == "READY_FOR_PICKUP"


async def test_return_with_damage_files_report_and_withholds_deposit(session):
    w = await _active_order(session, deposit="1000")

    result = await accept_return(session, w["order_id"], w["manager"], _return(
        ReturnDamage(
            game_copy_id=w["copy_id"], description="Missing dice",
            deposit_withheld=Decimal("300"),
        ),
    ))

    assert result.order.status == "COMPLETED"
    assert result.deposit_refund == Decimal("700.00")
    [report] = result.damage_reports
    assert report.game_copy_id == w["copy_id"]
    assert report.order_id == w["order_id"]
    assert report.reported_by == w["manager"]
    assert report.deposit_withheld == Decimal("300.00")
    assert report.resolved_at is None
    copy = await game_copy.get(session, w["copy_id"])
    assert (copy.status, copy.current_point_id) == ("DAMAGED", w["point"])


async def test_damaged_box_is_not_offered_to_the_next_client(session):
    w = await _active_order(session)
    await accept_return(session, w["order_id"], w["manager"], _return(
        ReturnDamage(game_copy_id=w["copy_id"], description="Torn board"),
    ))
    second = await make_client(session, "second@test.io")

    with pytest.raises(NotAvailableError):
        await create_order(session, second, order_request(w["point"], [w["game"]]))


async def test_only_the_reported_box_becomes_damaged(session):
    point = await make_point(session)
    manager = await make_manager(session, point)
    client_id = await make_client(session)
    dune = await make_game(session, "Dune")
    chess = await make_game(session, "Chess")
    dune_copy = await make_copy(session, dune, point, "INV-1")
    chess_copy = await make_copy(session, chess, point, "INV-2")
    order = await create_order(
        session, client_id, order_request(point, [dune, chess]),
    )
    await issue_order(session, order.id, manager)

    await accept_return(session, order.id, manager, _return(
        ReturnDamage(game_copy_id=dune_copy, description="Torn box"),
    ))

    assert (await game_copy.get(session, dune_copy)).status == "DAMAGED"
    assert (await game_copy.get(session, chess_copy)).status == "AVAILABLE"


async def test_return_can_be_accepted_at_another_point(session):
    w = await _active_order(session)
    other_point = await make_point(session, "North")
    other_manager = await make_manager(session, other_point, "other@test.io")

    await accept_return(session, w["order_id"], other_manager, _return())

    copy = await game_copy.get(session, w["copy_id"])
    assert (copy.status, copy.current_point_id) == ("AVAILABLE", other_point)


async def test_return_of_a_box_not_in_the_order_rejected(session):
    w = await _active_order(session)
    stray = await make_copy(session, w["game"], w["point"], "INV-2")

    with pytest.raises(ValueError):
        await accept_return(session, w["order_id"], w["manager"], _return(
            ReturnDamage(game_copy_id=stray, description="Not ours"),
        ))
    assert (await get_order(session, w["order_id"])).status == "ACTIVE"


async def test_withholding_more_than_the_deposit_rejected(session):
    w = await _active_order(session, deposit="1000")

    with pytest.raises(ValueError):
        await accept_return(session, w["order_id"], w["manager"], _return(
            ReturnDamage(
                game_copy_id=w["copy_id"], description="Destroyed",
                deposit_withheld=Decimal("1000.01"),
            ),
        ))
    assert (await get_order(session, w["order_id"])).status == "ACTIVE"


async def test_withholding_exactly_the_deposit_allowed(session):
    w = await _active_order(session, deposit="1000")

    result = await accept_return(session, w["order_id"], w["manager"], _return(
        ReturnDamage(
            game_copy_id=w["copy_id"], description="Destroyed",
            deposit_withheld=Decimal("1000"),
        ),
    ))

    assert result.deposit_refund == Decimal("0.00")


async def test_return_of_an_order_that_was_not_issued_refused(session):
    w = await _ready_order(session)

    with pytest.raises(InvalidTransitionError):
        await accept_return(session, w["order_id"], w["manager"], _return())


async def test_return_twice_refused(session):
    w = await _active_order(session)
    await accept_return(session, w["order_id"], w["manager"], _return())

    with pytest.raises(InvalidTransitionError):
        await accept_return(session, w["order_id"], w["manager"], _return())


async def test_return_of_unknown_order_not_found(session):
    w = await _ready_order(session)

    with pytest.raises(NotFoundError):
        await accept_return(session, 999999, w["manager"], _return())


def test_same_box_reported_twice_rejected_by_schema():
    with pytest.raises(ValidationError):
        _return(
            ReturnDamage(game_copy_id=1, description="a"),
            ReturnDamage(game_copy_id=1, description="b"),
        )


def test_negative_withheld_rejected_by_schema():
    with pytest.raises(ValidationError):
        ReturnDamage(
            game_copy_id=1, description="a", deposit_withheld=Decimal("-1"),
        )
