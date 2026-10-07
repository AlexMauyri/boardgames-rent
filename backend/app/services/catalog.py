"""Public, read-only catalog services."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import board_game, category, game_copy, pickup_point
from app.schemas import (
    BoardGameRead,
    CategoryRead,
    GameSearchItem,
    PickupPointRead,
)
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

async def list_games(
    session: AsyncSession,
    players: int | None = None,
    playtime_max: int | None = None,
    category_id: int | None = None,
    skip: int = 0,
    limit: int = 100,
) -> list[BoardGameRead]:
    """Browse the catalog, optionally filtered.

    Args:
        session: Active async session.
        players: Keep games whose supported player range includes this count.
            None disables the filter.
        playtime_max: Keep games whose average play time is at most this many
            minutes. None disables the filter.
        category_id: Keep games in this category. None disables the filter.
        skip: Rows to skip.
        limit: Maximum rows to return.

    Returns:
        Matching games, id-ascending; empty list if none.
    """
    rows = await board_game.list_filtered(
        session,
        players=players,
        playtime_max=playtime_max,
        category_id=category_id,
        skip=skip,
        limit=limit,
    )
    return [BoardGameRead.model_validate(row) for row in rows]


async def search_available_games(
    session: AsyncSession,
    pickup_point_id: int,
    players: int | None = None,
    playtime_max: int | None = None,
    category_id: int | None = None,
    skip: int = 0,
    limit: int = 100,
) -> list[GameSearchItem]:
    """Find games that fit the meeting and can reach the chosen point.

    Only games with at least one free box anywhere are returned. Games that
    can be collected at once come first; the rest need a delivery.

    Args:
        session: Active async session.
        pickup_point_id: Point where the client would collect the game.
        players: Number of players. None disables the filter.
        playtime_max: Maximum play time in minutes. None disables the filter.
        category_id: Required category. None disables the filter.
        skip: Results to skip.
        limit: Maximum results to return.

    Returns:
        Matching games with their stock; empty list if none.

    Raises:
        NotFoundError: No such pickup point.
        ValueError: The pickup point is not active.
    """
    point = await pickup_point.get(session, pickup_point_id)
    if point is None:
        raise NotFoundError("PickupPoint", pickup_point_id)
    if not point.is_active:
        raise ValueError("Pickup point is not active")

    # The stock filter is applied after the SQL filters, so paging happens
    # here and not in the query; the catalog is small.
    games = await board_game.list_filtered(
        session,
        players=players,
        playtime_max=playtime_max,
        category_id=category_id,
        limit=10_000,
    )
    free = await game_copy.count_free(session, [g.id for g in games])

    items: list[GameSearchItem] = []
    for game in games:
        at_point = free.get((game.id, pickup_point_id), 0)
        total = sum(n for (g, _), n in free.items() if g == game.id)
        if total == 0:
            continue
        items.append(GameSearchItem(
            game=BoardGameRead.model_validate(game),
            free_at_point=at_point,
            free_elsewhere=total - at_point,
        ))
    items.sort(key=lambda item: (item.free_at_point == 0, item.game.id))
    return items[skip:skip + limit]
