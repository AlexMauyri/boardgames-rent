"""Physical game box administration"""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import board_game, game_copy, pickup_point
from app.schemas import (
    GameCopyCreate,
    GameCopyRead,
    GameCopyStatus,
    GameCopyUpdate,
)
from app.services.exceptions import ConflictError, NotFoundError

_INVENTORY_CONSTRAINT = "uq_game_copies_inventory_number"


async def add_game_copy(
    session: AsyncSession,
    data: GameCopyCreate,
) -> GameCopyRead:
    """Register a new physical box; it starts AVAILABLE at the given point.

    Args:
        session: Active async session.
        data: Validated creation payload.

    Returns:
        The created box.

    Raises:
        NotFoundError: The game or the pickup point does not exist.
        ValueError: The pickup point is not active.
        ConflictError: A box with that inventory number already exists.
    """
    if await board_game.get(session, data.game_id) is None:
        raise NotFoundError("BoardGame", data.game_id)
    point = await pickup_point.get(session, data.current_point_id)
    if point is None:
        raise NotFoundError("PickupPoint", data.current_point_id)
    if not point.is_active:
        raise ValueError("Pickup point is not active")
    if await game_copy.get_by_inventory_number(session, data.inventory_number):
        raise ConflictError("GameCopy", data.inventory_number)

    try:
        obj = await game_copy.create(
            session,
            data={
                "game_id": data.game_id,
                "current_point_id": data.current_point_id,
                "inventory_number": data.inventory_number,
                "status": "AVAILABLE",
            },
        )
    except IntegrityError as exc:
        await session.rollback()
        if _INVENTORY_CONSTRAINT in str(exc):
            raise ConflictError("GameCopy", data.inventory_number) from exc
        raise

    result = GameCopyRead.model_validate(obj)
    await session.commit()
    return result


async def update_game_copy(
    session: AsyncSession,
    copy_id: int,
    data: GameCopyUpdate,
) -> GameCopyRead:
    """Edit a box's inventory number.

    Status and location are not editable here: they change only through the
    order, delivery and damage flows.

    Args:
        session: Active async session.
        copy_id: Primary key of the box.
        data: Partial update payload; unset fields are left alone.

    Returns:
        The updated box.

    Raises:
        NotFoundError: No box with that id.
        ConflictError: Another box already has that inventory number.
    """
    obj = await game_copy.get(session, copy_id)
    if obj is None:
        raise NotFoundError("GameCopy", copy_id)

    number = data.inventory_number
    if number is not None and number != obj.inventory_number:
        if await game_copy.get_by_inventory_number(session, number):
            raise ConflictError("GameCopy", number)
        obj.inventory_number = number
        try:
            await session.flush()
        except IntegrityError as exc:
            await session.rollback()
            raise ConflictError("GameCopy", number) from exc

    result = GameCopyRead.model_validate(obj)
    await session.commit()
    return result


async def get_game_copy(
    session: AsyncSession,
    copy_id: int,
) -> GameCopyRead:
    """Fetch a single box.

    Args:
        session: Active async session.
        copy_id: Primary key of the box.

    Returns:
        The box.

    Raises:
        NotFoundError: No box with that id.
    """
    obj = await game_copy.get(session, copy_id)
    if obj is None:
        raise NotFoundError("GameCopy", copy_id)
    return GameCopyRead.model_validate(obj)


async def list_game_copies(
    session: AsyncSession,
    game_id: int | None = None,
    point_id: int | None = None,
    status: GameCopyStatus | None = None,
    skip: int = 0,
    limit: int = 100,
) -> list[GameCopyRead]:
    """List boxes across all points, optionally filtered.

    Args:
        session: Active async session.
        game_id: Keep boxes of this catalog game. None disables it.
        point_id: Keep boxes currently at this point. None disables it.
        status: Keep boxes in this status. None disables it.
        skip: Rows to skip.
        limit: Maximum rows to return.

    Returns:
        Matching boxes, id-ascending; empty list if none.
    """
    rows = await game_copy.list_filtered(
        session,
        game_id=game_id,
        point_id=point_id,
        status=status,
        skip=skip,
        limit=limit,
    )
    return [GameCopyRead.model_validate(row) for row in rows]
