"""Tests for turning events into notifications (pure functions)."""

import pytest

from app.events import EventError, Recipient, build_notifications
from tests.conftest import make_event


def _one(event):
    notifications = build_notifications(event)
    assert len(notifications) == 1
    return notifications[0]


def test_order_created_goes_to_the_client():
    n = _one(make_event("order.created", {
        "order_id": 5, "client_id": 3, "pickup_point_id": 1,
        "status": "READY_FOR_PICKUP", "total_price": "900.00",
    }))

    assert n.recipient == Recipient("CLIENT", 3)
    assert n.payload["type"] == "order.created"
    assert n.payload["title"] == "Заказ оформлен"
    assert "№5" in n.payload["message"]
    assert n.payload["id"] == "evt-1"
    assert n.payload["created_at"] == "2026-11-03T10:00:00+00:00"
    assert n.payload["data"]["total_price"] == "900.00"


@pytest.mark.parametrize(
    ("status", "text"),
    [
        ("IN_TRANSIT", "в пути"),
        ("READY_FOR_PICKUP", "готов к выдаче"),
        ("ACTIVE", "выдана"),
        ("COMPLETED", "завершена"),
        ("CANCELLED", "отменён"),
    ],
)
def test_order_status_change_goes_to_the_client(status, text):
    n = _one(make_event("order.status_changed", {
        "order_id": 5, "client_id": 3, "pickup_point_id": 1,
        "old_status": "CREATED", "new_status": status,
    }))

    assert n.recipient == Recipient("CLIENT", 3)
    assert text in n.payload["message"]


def test_unknown_order_status_is_shown_verbatim():
    n = _one(make_event("order.status_changed", {
        "order_id": 5, "client_id": 3, "pickup_point_id": 1,
        "old_status": "A", "new_status": "WEIRD",
    }))

    assert "WEIRD" in n.payload["message"]


def test_new_delivery_goes_to_every_courier():
    n = _one(make_event("delivery.created", {
        "delivery_id": 9, "order_id": 5, "from_point_id": 2, "to_point_id": 1,
    }))

    assert n.recipient == Recipient("COURIER", None)
    assert n.payload["title"] == "Новая доставка"
    assert "из пункта №2 в пункт №1" in n.payload["message"]


@pytest.mark.parametrize(
    ("status", "text"),
    [("ACCEPTED", "принята"), ("IN_TRANSIT", "в пути"), ("DELIVERED", "доставлена")],
)
def test_delivery_status_change_goes_to_every_courier(status, text):
    n = _one(make_event("delivery.status_changed", {
        "delivery_id": 9, "order_id": 5, "courier_id": 4, "status": status,
    }))

    assert n.recipient == Recipient("COURIER", None)
    assert text in n.payload["message"]


def test_cancelled_delivery_goes_to_every_courier():
    n = _one(make_event("delivery.cancelled", {"delivery_id": 9, "order_id": 5}))

    assert n.recipient == Recipient("COURIER", None)
    assert "№9" in n.payload["message"]


def test_unknown_event_type_gives_no_notifications():
    assert build_notifications(make_event("something.else", {})) == []


@pytest.mark.parametrize(
    "event",
    [
        {},
        {"type": "order.created"},
        make_event("order.created", {"order_id": 1}),
        make_event("delivery.created", {"delivery_id": 1}),
        {"id": "x", "type": "order.created", "occurred_at": "t", "data": None},
    ],
    ids=["empty", "no-data", "no-client", "no-points", "null-data"],
)
def test_malformed_events_raise(event):
    with pytest.raises(EventError):
        build_notifications(event)
