"""Pickup point manager services: view the point, hand out, take back.

A manager works only on the point they are assigned to. The courier hands
boxes over through the delivery flow, so the manager's own handovers are the
two ends of a rental: issuing a box to the client and accepting it back.
"""

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import damage_report, employee, game_copy, order
from app.db.models import Employee
from app.schemas import (
    DamageReportRead,
    GameCopyRead,
    OrderDetailRead,
    OrderRead,
    OrderReturnCreate,
    OrderReturnResult,
    OrderStatus,
)
from app.services.exceptions import (
    ForbiddenError,
    InvalidTransitionError,
    NotFoundError,
)


async def require_manager(session: AsyncSession, manager_id: int) -> Employee:
    """Load an employee and ensure they are an active, assigned manager.

    Args:
        session: Active async session.
        manager_id: Primary key of the employee.

    Returns:
        The manager; `pickup_point_id` is guaranteed to be set.

    Raises:
        NotFoundError: No such employee.
        ForbiddenError: The employee is not an active manager.
    """
    row = await employee.get(session, manager_id)
    if row is None:
        raise NotFoundError("Employee", manager_id)
    if row.role != "MANAGER" or not row.is_active:
        raise ForbiddenError("Only an active manager can do this")
    return row


async def list_point_orders(
    session: AsyncSession,
    manager_id: int,
    status: OrderStatus | None = None,
    skip: int = 0,
    limit: int = 100,
) -> list[OrderRead]:
    """List orders collected at the manager's pickup point.

    Args:
        session: Active async session.
        manager_id: The manager.
        status: Keep only orders in this status. None disables it.
        skip: Rows to skip.
        limit: Maximum rows to return.

    Returns:
        Matching orders, newest first; empty list if none.

    Raises:
        NotFoundError: No such employee.
        ForbiddenError: The employee is not an active manager.
    """
    manager = await require_manager(session, manager_id)
    rows = await order.list_by_point(
        session, manager.pickup_point_id, status=status, skip=skip, limit=limit,
    )
    return [OrderRead.model_validate(row) for row in rows]


async def find_point_order(
    session: AsyncSession,
    manager_id: int,
    order_id: int,
) -> OrderDetailRead:
    """Look up an order by the number the client names.

    Args:
        session: Active async session.
        manager_id: The manager.
        order_id: The booking number.

    Returns:
        The order with its lines.

    Raises:
        NotFoundError: No such employee, or no such order at this point.
        ForbiddenError: The employee is not an active manager.
    """
    manager = await require_manager(session, manager_id)
    row = await order.get_detail(session, order_id)
    if row is None or row.pickup_point_id != manager.pickup_point_id:
        raise NotFoundError("Order", order_id)
    return OrderDetailRead.model_validate(row)


async def list_point_inventory(
    session: AsyncSession,
    manager_id: int,
    skip: int = 0,
    limit: int = 100,
) -> list[GameCopyRead]:
    """List the boxes physically at the manager's pickup point.

    Args:
        session: Active async session.
        manager_id: The manager.
        skip: Rows to skip.
        limit: Maximum rows to return.

    Returns:
        Boxes on the point's shelves, available or damaged; empty list if none.

    Raises:
        NotFoundError: No such employee.
        ForbiddenError: The employee is not an active manager.
    """
    manager = await require_manager(session, manager_id)
    rows = await game_copy.list_filtered(
        session, point_id=manager.pickup_point_id, skip=skip, limit=limit,
    )
    return [GameCopyRead.model_validate(row) for row in rows]


async def issue_order(
    session: AsyncSession,
    order_id: int,
    manager_id: int,
) -> OrderRead:
    """Hand the boxes to the client ("Выдать").

    The order becomes ACTIVE and its boxes leave the shelf.

    Args:
        session: Active async session.
        order_id: The booking number.
        manager_id: The manager; must work at the order's pickup point.

    Returns:
        The active order.

    Raises:
        NotFoundError: No such employee, or no such order at this point.
        ForbiddenError: The employee is not an active manager.
        InvalidTransitionError: The order is not READY_FOR_PICKUP, or a box
            is not on this point's shelf.
    """
    manager = await require_manager(session, manager_id)
    row = await order.get_for_update(session, order_id)
    if row is None or row.pickup_point_id != manager.pickup_point_id:
        raise NotFoundError("Order", order_id)
    if row.status != "READY_FOR_PICKUP":
        raise InvalidTransitionError("Order", order_id, row.status, "issue")

    copies = await game_copy.list_for_order(session, order_id, lock=True)
    missing = [
        c for c in copies
        if c.status != "AVAILABLE"
        or c.current_point_id != manager.pickup_point_id
    ]
    if missing:
        raise InvalidTransitionError(
            "Order", order_id, row.status,
            "issue: a box is not at the pickup point",
        )

    for copy in copies:
        copy.status = "WITH_CLIENT"
        copy.current_point_id = None
    row.status = "ACTIVE"
    await session.flush()

    result = OrderRead.model_validate(row)
    await session.commit()
    return result


async def accept_return(
    session: AsyncSession,
    order_id: int,
    manager_id: int,
    data: OrderReturnCreate,
) -> OrderReturnResult:
    """Take the boxes back, record damage and finish the rental.

    The boxes land on this manager's point, whichever point issued them.
    Boxes named in `data.damages` become DAMAGED; the rest become AVAILABLE.
    Whatever is withheld for damage reduces the deposit refund.

    Args:
        session: Active async session.
        order_id: The booking number.
        manager_id: The manager accepting the boxes.
        data: Inspection result; empty `damages` means all intact.

    Returns:
        The completed order, the reports filed and the deposit to refund.

    Raises:
        NotFoundError: No such employee or order.
        ForbiddenError: The employee is not an active manager.
        InvalidTransitionError: The order is not ACTIVE, or a box is not
            with the client.
        ValueError: A reported box is not in the order, or the amounts
            withheld exceed the deposit.
    """
    manager = await require_manager(session, manager_id)
    row = await order.get_for_update(session, order_id)
    if row is None:
        raise NotFoundError("Order", order_id)
    if row.status != "ACTIVE":
        raise InvalidTransitionError("Order", order_id, row.status, "return")

    copies = await game_copy.list_for_order(session, order_id, lock=True)
    if any(c.status != "WITH_CLIENT" for c in copies):
        raise InvalidTransitionError(
            "Order", order_id, row.status, "return: a box is not with the client",
        )

    order_copy_ids = {c.id for c in copies}
    for damage in data.damages:
        if damage.game_copy_id not in order_copy_ids:
            raise ValueError(
                f"Box {damage.game_copy_id} is not part of order {order_id}"
            )
    withheld = sum((d.deposit_withheld for d in data.damages), Decimal("0"))
    if withheld > row.deposit_paid:
        raise ValueError("Amount withheld exceeds the deposit paid")

    damaged_ids = {d.game_copy_id for d in data.damages}
    for copy in copies:
        copy.current_point_id = manager.pickup_point_id
        copy.status = "DAMAGED" if copy.id in damaged_ids else "AVAILABLE"

    reports = []
    for damage in data.damages:
        report = await damage_report.create(
            session,
            data={
                "game_copy_id": damage.game_copy_id,
                "order_id": order_id,
                "reported_by": manager.id,
                "description": damage.description,
                "deposit_withheld": damage.deposit_withheld,
            },
        )
        await session.refresh(report)
        reports.append(report)

    row.status = "COMPLETED"
    await session.flush()

    result = OrderReturnResult(
        order=OrderRead.model_validate(row),
        damage_reports=[DamageReportRead.model_validate(r) for r in reports],
        deposit_refund=row.deposit_paid - withheld,
    )
    await session.commit()
    return result
