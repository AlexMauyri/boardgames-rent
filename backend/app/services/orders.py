"""Client-facing order services: place, view, cancel.

Simplification: a box belongs to at most one open order at a time, whatever
the dates. Dates only drive the price. This keeps the physical location of
every box consistent without scheduling logic.
"""

from collections import Counter
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import (
    board_game,
    client,
    delivery,
    game_copy,
    order,
    pickup_point,
)
from app.schemas import OrderCreate, OrderDetailRead, OrderRead
from app.services.exceptions import (
    ForbiddenError,
    InvalidTransitionError,
    NotFoundError,
)
from app.services.fulfilment import plan_fulfilment
from app.services.pricing import calculate_price

# Statuses from which a client may still cancel: the boxes have not left a
# shelf yet, or have already arrived at the pickup point.
_CANCELLABLE = ("CREATED", "NEEDS_TRANSFER", "READY_FOR_PICKUP")

# Delivery statuses in which no box has physically moved yet.
_DELIVERY_NOT_STARTED = ("CREATED", "ACCEPTED")


async def create_order(
    session: AsyncSession,
    client_id: int,
    data: OrderCreate,
) -> OrderDetailRead:
    """Place a rental order.

    Chooses concrete boxes, prices the rental, and, when a box must come from
    another pickup point, creates the delivery task. The order starts as
    READY_FOR_PICKUP, or NEEDS_TRANSFER when a delivery was created.

    Args:
        session: Active async session.
        client_id: The ordering client.
        data: Validated order payload.

    Returns:
        The created order with its lines.

    Raises:
        ValueError: `start_date` is in the past, or the pickup point is not
            active.
        NotFoundError: The client, the pickup point or a game does not exist.
        ForbiddenError: The client account is disabled.
        NotAvailableError: The games cannot be supplied from current stock.
    """
    if data.start_date < date.today():
        raise ValueError("start_date must not be in the past")

    client_row = await client.get(session, client_id)
    if client_row is None:
        raise NotFoundError("Client", client_id)
    if not client_row.is_active:
        raise ForbiddenError("Client account is disabled")

    point = await pickup_point.get(session, data.pickup_point_id)
    if point is None:
        raise NotFoundError("PickupPoint", data.pickup_point_id)
    if not point.is_active:
        raise ValueError("Pickup point is not active")

    needed = Counter(data.game_ids)
    games = {g.id: g for g in await board_game.get_many(session, list(needed))}
    for game_id in sorted(needed):
        if game_id not in games:
            raise NotFoundError("BoardGame", game_id)

    # Lock every candidate box first: two concurrent orders for the same game
    # then queue up instead of both claiming the same box.
    candidates = await game_copy.list_available_for_games(
        session, list(needed), lock=True,
    )
    busy = await order.busy_copy_ids(session, [c.id for c in candidates])
    free = [c for c in candidates if c.id not in busy]
    plan = plan_fulfilment(free, needed, data.pickup_point_id)

    quote = calculate_price(
        [games[c.game_id].daily_price for c in plan.copies],
        [games[c.game_id].deposit_price for c in plan.copies],
        data.start_date,
        data.end_date,
    )
    transfer = plan.source_point_id is not None

    row = await order.create_with_items(
        session,
        values={
            "client_id": client_id,
            "pickup_point_id": data.pickup_point_id,
            "start_date": data.start_date,
            "end_date": data.end_date,
            "total_price": quote.total_price,
            "deposit_paid": quote.deposit,
            "status": "NEEDS_TRANSFER" if transfer else "READY_FOR_PICKUP",
        },
        items=[
            (c.id, games[c.game_id].daily_price) for c in plan.copies
        ],
    )
    if transfer:
        await delivery.create(
            session,
            data={
                "order_id": row.id,
                "from_point_id": plan.source_point_id,
                "to_point_id": data.pickup_point_id,
            },
        )

    detail = await order.get_detail(session, row.id)
    result = OrderDetailRead.model_validate(detail)
    await session.commit()
    return result


async def get_order(
    session: AsyncSession,
    order_id: int,
    client_id: int | None = None,
) -> OrderDetailRead:
    """Fetch an order with its lines.

    Args:
        session: Active async session.
        order_id: Primary key of the order.
        client_id: When given, the order must belong to this client; someone
            else's order is reported as missing so its existence is not
            leaked.

    Returns:
        The order with its lines.

    Raises:
        NotFoundError: No such order, or it belongs to another client.
    """
    row = await order.get_detail(session, order_id)
    if row is None or (client_id is not None and row.client_id != client_id):
        raise NotFoundError("Order", order_id)
    return OrderDetailRead.model_validate(row)


async def list_client_orders(
    session: AsyncSession,
    client_id: int,
    skip: int = 0,
    limit: int = 100,
) -> list[OrderRead]:
    """List a client's orders, newest first.

    Args:
        session: Active async session.
        client_id: The client.
        skip: Rows to skip.
        limit: Maximum rows to return.

    Returns:
        The client's orders without lines; empty list if none.
    """
    rows = await order.list_by_client(
        session, client_id, skip=skip, limit=limit,
    )
    return [OrderRead.model_validate(row) for row in rows]


async def cancel_order(
    session: AsyncSession,
    order_id: int,
    client_id: int,
) -> OrderRead:
    """Cancel a client's order and release its boxes.

    A delivery that has not started is deleted, since no box has moved. A
    finished delivery stays as history.

    Args:
        session: Active async session.
        order_id: Primary key of the order.
        client_id: The client asking; must own the order.

    Returns:
        The cancelled order.

    Raises:
        NotFoundError: No such order, or it belongs to another client.
        InvalidTransitionError: The order is in transit or already finished.
    """
    # Lock order: delivery first, then order, the same as the courier flows,
    # so concurrent cancel and accept cannot deadlock.
    task = await delivery.get_by_order(session, order_id, for_update=True)
    row = await order.get_for_update(session, order_id)
    if row is None or row.client_id != client_id:
        raise NotFoundError("Order", order_id)
    if row.status not in _CANCELLABLE:
        raise InvalidTransitionError("Order", order_id, row.status, "cancel")

    if task is not None and task.status in _DELIVERY_NOT_STARTED:
        await session.delete(task)
    row.status = "CANCELLED"
    await session.flush()

    result = OrderRead.model_validate(row)
    await session.commit()
    return result
