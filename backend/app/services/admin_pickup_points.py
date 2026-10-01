"""Pickup point administration"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import pickup_point
from app.schemas import PickupPointCreate, PickupPointRead, PickupPointUpdate
from app.services.exceptions import ConflictError, NotFoundError


async def list_pickup_points_admin(
    session: AsyncSession,
    skip: int = 0,
    limit: int = 100,
) -> list[PickupPointRead]:
    """Every pickup point, active and deactivated alike.

    Args:
        session: Active async session.
        skip: Rows to skip.
        limit: Maximum rows to return.

    Returns:
        Matching rows; empty list if none.
    """
    rows = await pickup_point.list(session, skip=skip, limit=limit)
    return [PickupPointRead.model_validate(row) for row in rows]


async def create_pickup_point(
    session: AsyncSession,
    data: PickupPointCreate,
) -> PickupPointRead:
    """Create a pickup point.

    Args:
        session: Active async session.
        data: Validated creation payload.

    Returns:
        The created pickup point.

    Raises:
        ConflictError: A pickup point with that name already exists.
    """
    existing = await pickup_point.get_by_name(session, data.name)
    if existing is not None:
        raise ConflictError("PickupPoint", data.name)

    obj = await pickup_point.create(session, data=data.model_dump())
    result = PickupPointRead.model_validate(obj)
    await session.commit()
    return result


async def update_pickup_point(
    session: AsyncSession,
    point_id: int,
    data: PickupPointUpdate,
) -> PickupPointRead:
    """Update a pickup point.

    Args:
        session: Active async session.
        point_id: Primary key of the pickup point.
        data: Partial update payload; unset fields are left alone.

    Returns:
        The updated pickup point.

    Raises:
        NotFoundError: No pickup point with that id.
        ConflictError: The new name belongs to a different pickup point.
    """
    current = await pickup_point.get(session, point_id)
    if current is None:
        raise NotFoundError("PickupPoint", point_id)

    if data.name is not None and data.name != current.name:
        clash = await pickup_point.get_by_name(session, data.name)
        if clash is not None and clash.id != point_id:
            raise ConflictError("PickupPoint", data.name)

    obj = await pickup_point.update(
        session,
        id=point_id,
        data=data.model_dump(exclude_unset=True),
    )
    result = PickupPointRead.model_validate(obj)
    await session.commit()
    return result


async def activate_pickup_point(
    session: AsyncSession,
    point_id: int,
) -> PickupPointRead:
    """Switch a pickup point back on.

    Args:
        session: Active async session.
        point_id: Primary key of the pickup point.

    Returns:
        The activated pickup point.

    Raises:
        NotFoundError: No pickup point with that id.
    """
    obj = await pickup_point.activate(session, id=point_id)
    if obj is None:
        raise NotFoundError("PickupPoint", point_id)
    result = PickupPointRead.model_validate(obj)
    await session.commit()
    return result


async def deactivate_pickup_point(
    session: AsyncSession,
    point_id: int,
) -> PickupPointRead:
    """Switch a pickup point off.

    Args:
        session: Active async session.
        point_id: Primary key of the pickup point.

    Returns:
        The deactivated pickup point.

    Raises:
        NotFoundError: No pickup point with that id.
    """
    obj = await pickup_point.deactivate(session, id=point_id)
    if obj is None:
        raise NotFoundError("PickupPoint", point_id)
    result = PickupPointRead.model_validate(obj)
    await session.commit()
    return result