"""Board game catalog administration"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import board_game, set_categories
from app.schemas import BoardGameCreate, BoardGameRead, BoardGameUpdate
from app.services.exceptions import NotFoundError


async def add_new_game_to_catalog(
    session: AsyncSession,
    data: BoardGameCreate,
) -> BoardGameRead:
    """Add a new game to the catalog.

    Args:
        session: Active async session.
        data: Validated creation payload, including `category_ids`.

    Returns:
        The created game.

    Raises:
        ValueError: One or more `category_ids` do not exist.
    """
    obj = await board_game.create_with_categories(session, data=data)
    result = BoardGameRead.model_validate(obj)
    await session.commit()
    return result


async def update_game(
    session: AsyncSession,
    game_id: int,
    data: BoardGameUpdate,
) -> BoardGameRead:
    """Update a board game.

    Args:
        session: Active async session.
        game_id: Primary key of the board game.
        data: Partial update payload; unset fields are left alone.

    Returns:
        The updated game.

    Raises:
        NotFoundError: No board game with that id.
        ValueError: `data` is inconsistent against the current row, or
            `category_ids` is present and contains unknown ids.
    """
    game = await board_game.get_with_categories(session, game_id)
    if game is None:
        raise NotFoundError("BoardGame", game_id)

    data.validate_against(game)

    obj = await board_game.update_with_categories(
        session,
        id=game_id,
        data=data,
    )

    result = BoardGameRead.model_validate(obj)
    await session.commit()
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
        ValueError: One or more `category_ids` do not exist.
    """
    game = await board_game.get_with_categories(session, game_id)
    if game is None:
        raise NotFoundError("BoardGame", game_id)

    await set_categories(session, game, category_ids)
    await session.flush()

    result = BoardGameRead.model_validate(game)
    await session.commit()
    return result