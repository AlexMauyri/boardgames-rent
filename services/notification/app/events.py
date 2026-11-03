"""Turn broker events into notifications for users.

Pure functions, no I/O. The API service publishes domain events (see
``services/backend/app/services/events.py``); the wording and the choice of
recipients live here.

Recipients: the order's client is notified of every change to their order;
all connected couriers are notified of delivery tasks appearing, being taken,
moving and disappearing, so their task lists stay current.
"""

from dataclasses import dataclass
from typing import Any

ROLE_CLIENT = "CLIENT"
ROLE_COURIER = "COURIER"

_ORDER_STATUS_TEXT = {
    "IN_TRANSIT": "Игра в пути в пункт выдачи",
    "READY_FOR_PICKUP": "Заказ готов к выдаче",
    "ACTIVE": "Игра выдана",
    "COMPLETED": "Аренда завершена",
    "CANCELLED": "Заказ отменён",
}

_DELIVERY_STATUS_TEXT = {
    "ACCEPTED": "принята курьером",
    "IN_TRANSIT": "в пути",
    "DELIVERED": "доставлена",
}


class EventError(Exception):
    """The event is malformed and cannot be turned into notifications."""


@dataclass(frozen=True)
class Recipient:
    """Who a notification is for.

    Attributes:
        role: Role of the recipient.
        user_id: Specific user, or None for every connected user of the role.
    """

    role: str
    user_id: int | None = None


@dataclass(frozen=True)
class Notification:
    """A message addressed to a recipient.

    Attributes:
        recipient: Who should receive it.
        payload: JSON object sent over the WebSocket.
    """

    recipient: Recipient
    payload: dict[str, Any]


def _text(event_type: str, data: dict[str, Any]) -> tuple[str, str, Recipient] | None:
    """Return ``(title, message, recipient)`` for a known event type."""
    if event_type == "order.created":
        return (
            "Заказ оформлен",
            f"Заказ №{data['order_id']} оформлен",
            Recipient(ROLE_CLIENT, int(data["client_id"])),
        )
    if event_type == "order.status_changed":
        status = data["new_status"]
        return (
            "Статус заказа изменён",
            f"Заказ №{data['order_id']}: "
            f"{_ORDER_STATUS_TEXT.get(status, status)}",
            Recipient(ROLE_CLIENT, int(data["client_id"])),
        )
    if event_type == "delivery.created":
        return (
            "Новая доставка",
            f"Новая доставка №{data['delivery_id']}: заказ №{data['order_id']}, "
            f"из пункта №{data['from_point_id']} в пункт №{data['to_point_id']}",
            Recipient(ROLE_COURIER),
        )
    if event_type == "delivery.status_changed":
        status = data["status"]
        return (
            "Статус доставки изменён",
            f"Доставка №{data['delivery_id']} "
            f"{_DELIVERY_STATUS_TEXT.get(status, status)}",
            Recipient(ROLE_COURIER),
        )
    if event_type == "delivery.cancelled":
        return (
            "Доставка отменена",
            f"Доставка №{data['delivery_id']} отменена: заказ №{data['order_id']} "
            "отменён клиентом",
            Recipient(ROLE_COURIER),
        )
    return None


def build_notifications(event: dict[str, Any]) -> list[Notification]:
    """Build the notifications an event calls for.

    Args:
        event: Decoded envelope with ``id``, ``type``, ``occurred_at`` and
            ``data``.

    Returns:
        Zero notifications for an event type this service does not know;
        otherwise one per recipient.

    Raises:
        EventError: The envelope or its ``data`` lacks a required field.
    """
    try:
        event_type = event["type"]
        data = event["data"]
        event_id = event["id"]
        occurred_at = event["occurred_at"]
        built = _text(event_type, data)
    except (KeyError, TypeError, ValueError) as exc:
        raise EventError(f"malformed event: {exc!r}") from exc

    if built is None:
        return []
    title, message, recipient = built
    return [Notification(
        recipient=recipient,
        payload={
            "id": event_id,
            "type": event_type,
            "title": title,
            "message": message,
            "data": data,
            "created_at": occurred_at,
        },
    )]
