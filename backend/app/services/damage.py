"""Damage handling outside a rental: routine inspections and repairs.

Damage found when a client returns a box is recorded by `accept_return`.
"""

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import damage_report, employee, game_copy, order
from app.schemas import DamageReportCreate, DamageReportRead
from app.services.exceptions import (
    ForbiddenError,
    InvalidTransitionError,
    NotFoundError,
)
from app.services.manager import require_manager


async def report_damage(
    session: AsyncSession,
    manager_id: int,
    data: DamageReportCreate,
) -> DamageReportRead:
    """Record damage found on a shelf during a routine inspection.

    The box becomes DAMAGED and is no longer offered to clients.

    Args:
        session: Active async session.
        manager_id: The manager filing the report.
        data: The report; `order_id` must be None and `deposit_withheld`
            zero, because no client is involved.

    Returns:
        The filed report.

    Raises:
        NotFoundError: No such employee or box.
        ForbiddenError: Not an active manager, or the box is at another point.
        InvalidTransitionError: The box is not on a shelf, or an open order
            holds it.
        ValueError: The report names an order or withholds a deposit.
    """
    manager = await require_manager(session, manager_id)
    if data.order_id is not None or data.deposit_withheld != 0:
        raise ValueError(
            "A routine report has no order and withholds no deposit; "
            "use accept_return for damage found at return"
        )

    copy = await game_copy.get_for_update(session, data.game_copy_id)
    if copy is None:
        raise NotFoundError("GameCopy", data.game_copy_id)
    if copy.current_point_id != manager.pickup_point_id:
        raise ForbiddenError("The box is not at your pickup point")
    if copy.status != "AVAILABLE":
        raise InvalidTransitionError(
            "GameCopy", copy.id, copy.status, "report damage",
        )
    if await order.busy_copy_ids(session, [copy.id]):
        raise InvalidTransitionError(
            "GameCopy", copy.id, copy.status,
            "report damage: an open order holds the box",
        )

    copy.status = "DAMAGED"
    report = await damage_report.create(
        session,
        data={
            "game_copy_id": copy.id,
            "reported_by": manager.id,
            "description": data.description,
        },
    )
    await session.refresh(report)

    result = DamageReportRead.model_validate(report)
    await session.commit()
    return result


async def resolve_damage_report(
    session: AsyncSession,
    report_id: int,
    employee_id: int,
) -> DamageReportRead:
    """Mark a box as repaired.

    When no other report on the box is still open, the box becomes AVAILABLE
    again.

    Args:
        session: Active async session.
        report_id: Primary key of the report.
        employee_id: An admin, or the manager of the point holding the box.

    Returns:
        The resolved report.

    Raises:
        NotFoundError: No such employee or report.
        ForbiddenError: Not an active admin, nor the manager of the box's point.
        InvalidTransitionError: The report is already resolved.
    """
    actor = await employee.get(session, employee_id)
    if actor is None:
        raise NotFoundError("Employee", employee_id)
    if not actor.is_active or actor.role not in ("ADMIN", "MANAGER"):
        raise ForbiddenError("Only an admin or a manager can resolve reports")

    report = await damage_report.get_for_update(session, report_id)
    if report is None:
        raise NotFoundError("DamageReport", report_id)
    if report.resolved_at is not None:
        raise InvalidTransitionError(
            "DamageReport", report_id, "RESOLVED", "resolve",
        )

    copy = await game_copy.get_for_update(session, report.game_copy_id)
    if actor.role == "MANAGER" and copy.current_point_id != actor.pickup_point_id:
        raise ForbiddenError("The box is not at your pickup point")

    report.resolved_at = datetime.now(UTC)
    still_open = await damage_report.count_open_for_copy(
        session, copy.id, exclude_id=report.id,
    )
    if copy.status == "DAMAGED" and still_open == 0:
        copy.status = "AVAILABLE"
    await session.flush()

    result = DamageReportRead.model_validate(report)
    await session.commit()
    return result
