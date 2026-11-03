"""Tests for the domain events the service layer publishes."""

from app.crud import delivery as delivery_crud
from app.schemas import OrderReturnCreate
from app.services import (
    accept_delivery,
    accept_return,
    cancel_order,
    complete_delivery,
    create_order,
    issue_order,
    start_delivery,
)
from app.services.events import emit
from tests.helpers import (
    make_client,
    make_copy,
    make_courier,
    make_game,
    make_manager,
    make_point,
    order_request,
)


class _Recorder:
    """Collects published events as ``(type, data)`` pairs."""

    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    async def publish(self, event_type, data):
        self.events.append((event_type, data))

    def types(self) -> list[str]:
        return [t for t, _ in self.events]

    def of(self, event_type: str) -> list[dict]:
        return [d for t, d in self.events if t == event_type]


class _Broken:
    async def publish(self, event_type, data):
        raise ConnectionError("broker down")


async def _transfer_world(session):
    """A client, a courier, a manager and a box that must travel North -> Center."""
    here = await make_point(session, "Center")
    north = await make_point(session, "North")
    client_id = await make_client(session)
    courier = await make_courier(session)
    manager = await make_manager(session, here)
    game = await make_game(session)
    await make_copy(session, game, north, "INV-1")
    return dict(here=here, north=north, client=client_id, courier=courier,
                manager=manager, game=game)


async def test_order_without_transfer_publishes_only_order_created(session):
    point = await make_point(session)
    game = await make_game(session)
    await make_copy(session, game, point, "INV-1")
    client_id = await make_client(session)
    events = _Recorder()

    order = await create_order(
        session, client_id, order_request(point, [game]), events=events,
    )

    assert events.types() == ["order.created"]
    created = events.of("order.created")[0]
    assert created["order_id"] == order.id
    assert created["client_id"] == client_id
    assert created["pickup_point_id"] == point
    assert created["status"] == "READY_FOR_PICKUP"


async def test_order_with_transfer_also_publishes_delivery_created(session):
    w = await _transfer_world(session)
    events = _Recorder()

    order = await create_order(
        session, w["client"], order_request(w["here"], [w["game"]]),
        events=events,
    )

    assert events.types() == ["order.created", "delivery.created"]
    task = await delivery_crud.get_by_order(session, order.id)
    assert events.of("delivery.created") == [{
        "delivery_id": task.id,
        "order_id": order.id,
        "from_point_id": w["north"],
        "to_point_id": w["here"],
    }]


async def test_full_flow_publishes_every_status_change(session):
    w = await _transfer_world(session)
    order = await create_order(
        session, w["client"], order_request(w["here"], [w["game"]]),
    )
    task = await delivery_crud.get_by_order(session, order.id)
    events = _Recorder()

    await accept_delivery(session, task.id, w["courier"], events=events)
    await start_delivery(session, task.id, w["courier"], events=events)
    await complete_delivery(session, task.id, w["courier"], events=events)
    await issue_order(session, order.id, w["manager"], events=events)
    await accept_return(
        session, order.id, w["manager"], OrderReturnCreate(), events=events,
    )

    deliveries = [d["status"] for d in events.of("delivery.status_changed")]
    assert deliveries == ["ACCEPTED", "IN_TRANSIT", "DELIVERED"]
    assert {d["courier_id"] for d in events.of("delivery.status_changed")} == {w["courier"]}
    transitions = [
        (d["old_status"], d["new_status"])
        for d in events.of("order.status_changed")
    ]
    assert transitions == [
        ("NEEDS_TRANSFER", "IN_TRANSIT"),
        ("IN_TRANSIT", "READY_FOR_PICKUP"),
        ("READY_FOR_PICKUP", "ACTIVE"),
        ("ACTIVE", "COMPLETED"),
    ]
    assert {d["client_id"] for d in events.of("order.status_changed")} == {w["client"]}


async def test_cancel_publishes_status_change_and_delivery_cancelled(session):
    w = await _transfer_world(session)
    order = await create_order(
        session, w["client"], order_request(w["here"], [w["game"]]),
    )
    task = await delivery_crud.get_by_order(session, order.id)
    events = _Recorder()

    await cancel_order(session, order.id, w["client"], events=events)

    assert events.of("order.status_changed")[0]["new_status"] == "CANCELLED"
    assert events.of("order.status_changed")[0]["old_status"] == "NEEDS_TRANSFER"
    assert events.of("delivery.cancelled") == [
        {"delivery_id": task.id, "order_id": order.id},
    ]


async def test_cancel_without_delivery_has_no_delivery_event(session):
    point = await make_point(session)
    game = await make_game(session)
    await make_copy(session, game, point, "INV-1")
    client_id = await make_client(session)
    order = await create_order(session, client_id, order_request(point, [game]))
    events = _Recorder()

    await cancel_order(session, order.id, client_id, events=events)

    assert events.types() == ["order.status_changed"]


async def test_broker_failure_does_not_fail_the_request(session):
    point = await make_point(session)
    game = await make_game(session)
    await make_copy(session, game, point, "INV-1")
    client_id = await make_client(session)

    order = await create_order(
        session, client_id, order_request(point, [game]), events=_Broken(),
    )

    assert order.status == "READY_FOR_PICKUP"


async def test_emit_without_publisher_is_a_no_op():
    await emit(None, "order.created", {"order_id": 1})
