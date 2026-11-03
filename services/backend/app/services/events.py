"""Domain events published to the message broker.

The service layer reports what happened and does not know who to tell: the
Notification Service turns events into messages for users. Publishing is
best effort and happens after the database commit, so a broker outage never
fails or rolls back a request.

Event types and their ``data``:

    order.created           order_id, client_id, pickup_point_id, status, total_price
    order.status_changed    order_id, client_id, pickup_point_id, old_status, new_status
    delivery.created        delivery_id, order_id, from_point_id, to_point_id
    delivery.status_changed delivery_id, order_id, courier_id, status
    delivery.cancelled      delivery_id, order_id
"""

import logging
from typing import Any, Protocol

logger = logging.getLogger(__name__)

ORDER_CREATED = "order.created"
ORDER_STATUS_CHANGED = "order.status_changed"
DELIVERY_CREATED = "delivery.created"
DELIVERY_STATUS_CHANGED = "delivery.status_changed"
DELIVERY_CANCELLED = "delivery.cancelled"


class EventPublisher(Protocol):
    """Anything that can publish an event, e.g. the RabbitMQ publisher."""

    async def publish(self, event_type: str, data: dict[str, Any]) -> None:
        """Publish one event; ``event_type`` doubles as the routing key."""


async def emit(
    publisher: EventPublisher | None,
    event_type: str,
    data: dict[str, Any],
) -> None:
    """Publish an event, swallowing any broker failure.

    Args:
        publisher: The broker publisher, or None when events are disabled.
        event_type: One of the event type constants.
        data: JSON-serialisable event payload.
    """
    if publisher is None:
        return
    try:
        await publisher.publish(event_type, data)
    except Exception:
        logger.exception("event publish failed type=%s", event_type)


async def emit_order_status_changed(
    publisher: EventPublisher | None,
    order: Any,
    old_status: str,
) -> None:
    """Publish ``order.status_changed`` for an order row or schema.

    Args:
        publisher: The broker publisher, or None.
        order: Anything with ``id``, ``client_id``, ``pickup_point_id`` and
            ``status`` — the order after the transition.
        old_status: The status before the transition.
    """
    await emit(publisher, ORDER_STATUS_CHANGED, {
        "order_id": order.id,
        "client_id": order.client_id,
        "pickup_point_id": order.pickup_point_id,
        "old_status": old_status,
        "new_status": order.status,
    })


async def emit_delivery_status_changed(
    publisher: EventPublisher | None,
    delivery: Any,
) -> None:
    """Publish ``delivery.status_changed`` for a delivery row or schema."""
    await emit(publisher, DELIVERY_STATUS_CHANGED, {
        "delivery_id": delivery.id,
        "order_id": delivery.order_id,
        "courier_id": delivery.courier_id,
        "status": delivery.status,
    })
