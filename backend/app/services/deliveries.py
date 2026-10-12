"""Courier services: see open tasks, accept, pick up, hand over.

Lifecycle of a delivery and what it does to the order and the boxes:

    CREATED --accept--> ACCEPTED --start--> IN_TRANSIT --complete--> DELIVERED
    order:  NEEDS_TRANSFER        NEEDS_TRANSFER   IN_TRANSIT      READY_FOR_PICKUP
    boxes:  on source shelf       on source shelf  IN_TRANSIT       AVAILABLE at
            (AVAILABLE)           -> IN_TRANSIT    (no point)       destination

Only the boxes that are at the departure point travel; boxes of the same
order already at the destination stay on their shelf.
"""

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import delivery, employee, game_copy, order
from app.db.models import Delivery
from app.schemas import DeliveryRead
from app.services.exceptions import (
    ForbiddenError,
    InvalidTransitionError,
    NotFoundError,
)


async def list_open_deliveries(
    session: AsyncSession,
    skip: int = 0,
    limit: int = 100,
) -> list[DeliveryRead]:
    """List tasks that no courier has accepted yet.

    Args:
        session: Active async session.
        skip: Rows to skip.
        limit: Maximum rows to return.

    Returns:
        Open tasks, oldest first; empty list if none.
    """
    rows = await delivery.list_open(session, skip=skip, limit=limit)
    return [DeliveryRead.model_validate(row) for row in rows]


async def list_courier_deliveries(
    session: AsyncSession,
    courier_id: int,
    active_only: bool = True,
    skip: int = 0,
    limit: int = 100,
) -> list[DeliveryRead]:
    """List a courier's tasks.

    Args:
        session: Active async session.
        courier_id: The courier.
        active_only: When True, only accepted and in-transit tasks.
        skip: Rows to skip.
        limit: Maximum rows to return.

    Returns:
        The courier's tasks, oldest first; empty list if none.
    """
    rows = await delivery.list_by_courier(
        session, courier_id, active_only=active_only, skip=skip, limit=limit,
    )
    return [DeliveryRead.model_validate(row) for row in rows]


async def _require_courier(session: AsyncSession, courier_id: int) -> None:
    """Ensure the id belongs to an active employee with role COURIER.

    Raises:
        NotFoundError: No such employee.
        ForbiddenError: The employee is not an active courier.
    """
    row = await employee.get(session, courier_id)
    if row is None:
        raise NotFoundError("Employee", courier_id)
    if row.role != "COURIER" or not row.is_active:
        raise ForbiddenError("Only an active courier can work on deliveries")


async def _lock_own(
    session: AsyncSession,
    delivery_id: int,
    courier_id: int,
) -> Delivery:
    """Lock a delivery and ensure it is assigned to this courier.

    Raises:
        NotFoundError: No such delivery.
        ForbiddenError: The delivery is not assigned to this courier.
    """
    await _require_courier(session, courier_id)
    row = await delivery.get_for_update(session, delivery_id)
    if row is None:
        raise NotFoundError("Delivery", delivery_id)
    if row.courier_id != courier_id:
        raise ForbiddenError("Delivery is not assigned to this courier")
    return row


async def accept_delivery(
    session: AsyncSession,
    delivery_id: int,
    courier_id: int,
) -> DeliveryRead:
    """Take an open task ("Принять заказ").

    Args:
        session: Active async session.
        delivery_id: Primary key of the delivery.
        courier_id: The courier taking the task.

    Returns:
        The accepted delivery.

    Raises:
        NotFoundError: No such delivery or courier.
        ForbiddenError: The employee is not an active courier.
        InvalidTransitionError: Someone already accepted the task.
    """
    await _require_courier(session, courier_id)
    row = await delivery.get_for_update(session, delivery_id)
    if row is None:
        raise NotFoundError("Delivery", delivery_id)
    if row.status != "CREATED" or row.courier_id is not None:
        raise InvalidTransitionError(
            "Delivery", delivery_id, row.status, "accept",
        )

    row.courier_id = courier_id
    row.status = "ACCEPTED"
    await session.flush()

    result = DeliveryRead.model_validate(row)
    await session.commit()
    return result


async def start_delivery(
    session: AsyncSession,
    delivery_id: int,
    courier_id: int,
) -> DeliveryRead:
    """Mark the boxes as picked up and on the road ("Забрал, в пути").

    Args:
        session: Active async session.
        delivery_id: Primary key of the delivery.
        courier_id: The courier; must be the one who accepted the task.

    Returns:
        The delivery in transit.

    Raises:
        NotFoundError: No such delivery or courier.
        ForbiddenError: Not an active courier, or not this courier's task.
        InvalidTransitionError: The task is not in ACCEPTED, or no box is at
            the departure point.
    """
    row = await _lock_own(session, delivery_id, courier_id)
    if row.status != "ACCEPTED":
        raise InvalidTransitionError(
            "Delivery", delivery_id, row.status, "start",
        )

    parent = await order.get_for_update(session, row.order_id)
    copies = await game_copy.list_for_order(session, row.order_id, lock=True)
    moving = [
        c for c in copies
        if c.status == "AVAILABLE" and c.current_point_id == row.from_point_id
    ]
    if not moving:
        raise InvalidTransitionError(
            "Delivery", delivery_id, row.status,
            "start: no box at the departure point",
        )

    for copy in moving:
        copy.status = "IN_TRANSIT"
        copy.current_point_id = None
    row.status = "IN_TRANSIT"
    parent.status = "IN_TRANSIT"
    await session.flush()

    result = DeliveryRead.model_validate(row)
    await session.commit()
    return result


async def complete_delivery(
    session: AsyncSession,
    delivery_id: int,
    courier_id: int,
) -> DeliveryRead:
    """Hand the boxes over at the destination ("Доставлено").

    The order becomes READY_FOR_PICKUP; the manager then checks the boxes.

    Args:
        session: Active async session.
        delivery_id: Primary key of the delivery.
        courier_id: The courier; must be the one carrying the boxes.

    Returns:
        The finished delivery.

    Raises:
        NotFoundError: No such delivery or courier.
        ForbiddenError: Not an active courier, or not this courier's task.
        InvalidTransitionError: The task is not in IN_TRANSIT.
    """
    row = await _lock_own(session, delivery_id, courier_id)
    if row.status != "IN_TRANSIT":
        raise InvalidTransitionError(
            "Delivery", delivery_id, row.status, "complete",
        )

    parent = await order.get_for_update(session, row.order_id)
    copies = await game_copy.list_for_order(session, row.order_id, lock=True)
    for copy in copies:
        if copy.status == "IN_TRANSIT":
            copy.status = "AVAILABLE"
            copy.current_point_id = row.to_point_id
    row.status = "DELIVERED"
    row.delivered_at = datetime.now(UTC)
    parent.status = "READY_FOR_PICKUP"
    await session.flush()

    result = DeliveryRead.model_validate(row)
    await session.commit()
    return result
