"""Public, read-only catalog services."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import board_game, category, pickup_point
from app.schemas import BoardGameRead, CategoryRead, PickupPointRead
from app.services.exceptions import NotFoundError


async def list_categories(
    session: AsyncSession,
    skip: int = 0,
    limit: int = 100,
) -> list[CategoryRead]:
    """List all categories, id-ascending.

    Args:
        session: Active async session.
        skip: Rows to skip.
        limit: Maximum rows to return.

    Returns:
        Matching rows; empty list if none.
    """
    rows = await category.list(session, skip=skip, limit=limit)
    return [CategoryRead.model_validate(row) for row in rows]


async def list_pickup_points_public(
    session: AsyncSession,
    skip: int = 0,
    limit: int = 100,
) -> list[PickupPointRead]:
    """List active pickup points, id-ascending.

    Args:
        session: Active async session.
        skip: Rows to skip.
        limit: Maximum rows to return.

    Returns:
        Active rows; empty list if none.
    """
    rows = await pickup_point.list_active(session, skip=skip, limit=limit)
    return [PickupPointRead.model_validate(row) for row in rows]


async def get_game_detail(
    session: AsyncSession,
    game_id: int,
) -> BoardGameRead:
    """Fetch a single board game by id.

    Args:
        session: Active async session.
        game_id: Primary key of the board game.

    Returns:
        The board game.

    Raises:
        NotFoundError: No board game with that id.
    """
    obj = await board_game.get_with_categories(session, game_id)
    if obj is None:
        raise NotFoundError("BoardGame", game_id)
    return BoardGameRead.model_validate(obj)