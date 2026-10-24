"""Board game catalog administration"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import board_game, set_categories
from app.schemas import BoardGameCreate, BoardGameRead, BoardGameUpdate
from app.services.exceptions import NotFoundError, ServiceValueError

logger = logging.getLogger(__name__)


async def add_new_game_to_catalog(
    session: AsyncSession,
    data: BoardGameCreate,
) -> BoardGameRead:
    """Add a new game to the catalog."""
    scalar_data = data.model_dump(exclude={"category_ids"})
    try:
        obj = await board_game.create_with_categories(
            session,
            data=scalar_data,
            category_ids=data.category_ids,
        )
    except ValueError as exc:
        logger.warning(
            "game creation rejected title=%s reason=unknown_category_ids",
            data.title,
        )
        raise ServiceValueError(str(exc)) from exc

    result = BoardGameRead.model_validate(obj)
    await session.commit()
    logger.info(
        "game created game_id=%s title=%s category_count=%s",
        result.id, result.title, len(data.category_ids),
    )
    return result


async def update_game(
    session: AsyncSession,
    game_id: int,
    data: BoardGameUpdate,
) -> BoardGameRead:
    """Update a board game."""
    game = await board_game.get_with_categories(session, game_id)
    if game is None:
        raise NotFoundError("BoardGame", game_id)

    try:
        data.validate_against(game)
    except ValueError as exc:
        logger.warning(
            "game update rejected game_id=%s reason=invalid_player_range",
            game_id,
        )
        raise ServiceValueError(str(exc)) from exc

    scalar_data = data.model_dump(exclude_unset=True, exclude={"category_ids"})
    category_ids: list[int] | None = (
        data.category_ids or []
        if "category_ids" in data.model_fields_set
        else None
    )

    try:
        obj = await board_game.update_with_categories(
            session,
            id=game_id,
            data=scalar_data,
            category_ids=category_ids,
        )
    except ValueError as exc:
        logger.warning(
            "game update rejected game_id=%s reason=unknown_category_ids",
            game_id,
        )
        raise ServiceValueError(str(exc)) from exc

    result = BoardGameRead.model_validate(obj)
    await session.commit()
    logger.info(
        "game updated game_id=%s changed_fields=%s",
        game_id, sorted(data.model_fields_set),
    )
    return result


async def set_game_categories(
    session: AsyncSession,
    game_id: int,
    category_ids: list[int],
) -> BoardGameRead:
    """Replace a game's full category set.

    Args:
        session: Active async session.
        game_id: Primary key of the board game.
        category_ids: The complete desired set of category ids. An empty list
            clears all categories.

    Returns:
        The game with its updated category set.

    Raises:
        NotFoundError: No board game with that id.
        ServiceValueError: One or more `category_ids` do not exist.
    """
    game = await board_game.get_with_categories(session, game_id)
    if game is None:
        raise NotFoundError("BoardGame", game_id)

    try:
        await set_categories(session, game, category_ids)
    except ValueError as exc:
        logger.warning(
            "game categories update rejected game_id=%s reason=unknown_category_ids",
            game_id,
        )
        raise ServiceValueError(str(exc)) from exc

    await session.flush()

    result = BoardGameRead.model_validate(game)
    await session.commit()
    logger.info(
        "game categories replaced game_id=%s category_count=%s",
        game_id, len(category_ids),
    )
    return result