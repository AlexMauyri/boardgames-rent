"""Tests for routine damage reports and their resolution."""

from decimal import Decimal

import pytest

from app.crud import game_copy
from app.schemas import DamageReportCreate, OrderReturnCreate, ReturnDamage
from app.services import (
    ForbiddenError,
    InvalidTransitionError,
    NotAvailableError,
    NotFoundError,
    accept_return,
    create_order,
    issue_order,
    report_damage,
    resolve_damage_report,
)
from tests.helpers import (
    make_client,
    make_copy,
    make_courier,
    make_employee,
    make_game,
    make_manager,
    make_point,
    order_request,
)


async def _shelf(session):
    """A manager and one box on the shelf of their point."""
    point = await make_point(session, "Center")
    manager = await make_manager(session, point)
    game = await make_game(session)
    copy_id = await make_copy(session, game, point, "INV-1")
    return dict(point=point, manager=manager, game=game, copy_id=copy_id)


def _report(copy_id: int, **overrides) -> DamageReportCreate:
    values = dict(game_copy_id=copy_id, description="Torn box")
    values.update(overrides)
    return DamageReportCreate(**values)


async def test_routine_report_marks_the_box_damaged(session):
    w = await _shelf(session)

    report = await report_damage(session, w["manager"], _report(w["copy_id"]))

    assert report.game_copy_id == w["copy_id"]
    assert report.order_id is None
    assert report.reported_by == w["manager"]
    assert report.deposit_withheld == Decimal("0")
    assert report.resolved_at is None
    copy = await game_copy.get(session, w["copy_id"])
    assert (copy.status, copy.current_point_id) == ("DAMAGED", w["point"])


async def test_damaged_box_is_not_offered_to_clients(session):
    w = await _shelf(session)
    client_id = await make_client(session)
    await report_damage(session, w["manager"], _report(w["copy_id"]))

    with pytest.raises(NotAvailableError):
        await create_order(session, client_id, order_request(w["point"], [w["game"]]))


async def test_report_on_box_of_another_point_forbidden(session):
    w = await _shelf(session)
    other_point = await make_point(session, "North")
    other_manager = await make_manager(session, other_point, "other@test.io")

    with pytest.raises(ForbiddenError):
        await report_damage(session, other_manager, _report(w["copy_id"]))


async def test_report_on_unknown_box_not_found(session):
    w = await _shelf(session)

    with pytest.raises(NotFoundError):
        await report_damage(session, w["manager"], _report(999999))


async def test_report_on_box_held_by_open_order_refused(session):
    w = await _shelf(session)
    client_id = await make_client(session)
    await create_order(session, client_id, order_request(w["point"], [w["game"]]))

    with pytest.raises(InvalidTransitionError):
        await report_damage(session, w["manager"], _report(w["copy_id"]))
    assert (await game_copy.get(session, w["copy_id"])).status == "AVAILABLE"


async def test_report_on_box_with_a_client_refused(session):
    w = await _shelf(session)
    client_id = await make_client(session)
    order = await create_order(
        session, client_id, order_request(w["point"], [w["game"]]),
    )
    await issue_order(session, order.id, w["manager"])

    # The box is with the client: not at the manager's point.
    with pytest.raises(ForbiddenError):
        await report_damage(session, w["manager"], _report(w["copy_id"]))


async def test_second_report_on_already_damaged_box_refused(session):
    w = await _shelf(session)
    await report_damage(session, w["manager"], _report(w["copy_id"]))

    with pytest.raises(InvalidTransitionError):
        await report_damage(session, w["manager"], _report(w["copy_id"]))


async def test_routine_report_cannot_name_an_order_or_withhold_deposit(session):
    w = await _shelf(session)

    with pytest.raises(ValueError):
        await report_damage(
            session, w["manager"], _report(w["copy_id"], order_id=1),
        )
    with pytest.raises(ValueError):
        await report_damage(
            session, w["manager"],
            _report(w["copy_id"], deposit_withheld=Decimal("10")),
        )


async def test_non_manager_cannot_report(session):
    w = await _shelf(session)
    courier = await make_courier(session)

    with pytest.raises(ForbiddenError):
        await report_damage(session, courier, _report(w["copy_id"]))


async def test_resolving_returns_the_box_to_service(session):
    w = await _shelf(session)
    report = await report_damage(session, w["manager"], _report(w["copy_id"]))

    resolved = await resolve_damage_report(session, report.id, w["manager"])

    assert resolved.resolved_at is not None
    copy = await game_copy.get(session, w["copy_id"])
    assert (copy.status, copy.current_point_id) == ("AVAILABLE", w["point"])


async def test_box_stays_damaged_while_another_report_is_open(session):
    w = await _shelf(session)
    first = await report_damage(session, w["manager"], _report(w["copy_id"]))
    # A second, order-linked report on the same box (as accept_return files).
    from app.crud import damage_report

    await damage_report.create(session, data={
        "game_copy_id": w["copy_id"], "reported_by": w["manager"],
        "description": "Also a missing card",
    })
    await session.commit()

    await resolve_damage_report(session, first.id, w["manager"])

    assert (await game_copy.get(session, w["copy_id"])).status == "DAMAGED"


async def test_resolving_twice_refused(session):
    w = await _shelf(session)
    report = await report_damage(session, w["manager"], _report(w["copy_id"]))
    await resolve_damage_report(session, report.id, w["manager"])

    with pytest.raises(InvalidTransitionError):
        await resolve_damage_report(session, report.id, w["manager"])


async def test_admin_can_resolve_a_report_anywhere(session):
    w = await _shelf(session)
    admin = await make_employee(session, "ADMIN", "admin@test.io")
    report = await report_damage(session, w["manager"], _report(w["copy_id"]))

    resolved = await resolve_damage_report(session, report.id, admin)

    assert resolved.resolved_at is not None


async def test_manager_of_another_point_cannot_resolve(session):
    w = await _shelf(session)
    other_point = await make_point(session, "North")
    other_manager = await make_manager(session, other_point, "other@test.io")
    report = await report_damage(session, w["manager"], _report(w["copy_id"]))

    with pytest.raises(ForbiddenError):
        await resolve_damage_report(session, report.id, other_manager)


async def test_courier_cannot_resolve(session):
    w = await _shelf(session)
    courier = await make_courier(session)
    report = await report_damage(session, w["manager"], _report(w["copy_id"]))

    with pytest.raises(ForbiddenError):
        await resolve_damage_report(session, report.id, courier)


async def test_resolve_unknown_report_not_found(session):
    w = await _shelf(session)

    with pytest.raises(NotFoundError):
        await resolve_damage_report(session, 999999, w["manager"])


async def test_damage_found_at_return_can_be_resolved_too(session):
    w = await _shelf(session)
    client_id = await make_client(session)
    order = await create_order(
        session, client_id, order_request(w["point"], [w["game"]]),
    )
    await issue_order(session, order.id, w["manager"])
    result = await accept_return(
        session, order.id, w["manager"],
        OrderReturnCreate(damages=[
            ReturnDamage(game_copy_id=w["copy_id"], description="Torn board"),
        ]),
    )
    [report] = result.damage_reports

    await resolve_damage_report(session, report.id, w["manager"])

    assert (await game_copy.get(session, w["copy_id"])).status == "AVAILABLE"
