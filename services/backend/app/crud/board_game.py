"""CRUD for board games, plus the M:N link helper."""

from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.crud.base import CRUDBase
from app.db.models import BoardGame, Category
from app.schemas import BoardGameCreate, BoardGameUpdate


async def _load_categories(
    session: AsyncSession,
    category_ids: list[int],
) -> list[Category]:
    """Load the categories with the given ids, one query, deduplicated.

    Args:
        session: Active async session.
        category_ids: Category primary keys to resolve. Duplicates are
            collapsed; order is not preserved.

    Returns:
        The matching categories. Empty list when `category_ids` is empty.

    Raises:
        ValueError: One or more ids in `category_ids` do not exist. The
            message lists the missing ids in sorted order.
    """
    unique_ids = set(category_ids)
    if not unique_ids:
        return []
    stmt = select(Category).where(Category.id.in_(unique_ids))
    result = await session.execute(stmt)
    loaded = list(result.scalars().all())
    if len(loaded) != len(unique_ids):
        found = {c.id for c in loaded}
        missing = sorted(unique_ids - found)
        raise ValueError(f"Unknown category ids: {missing}")
    return loaded


async def set_categories(
    session: AsyncSession,
    game: BoardGame,
    category_ids: list[int],
) -> None:
    """Replace a game's full category set.

    Args:
        session: Active async session.
        game: The board game whose categories are being replaced. Must be
            either pending (not yet flushed) or loaded with
            `selectinload(BoardGame.categories)`. On a persistent instance
            whose collection was never loaded, the unit of work cannot
            compute the diff and `lazy="raise"` will not fetch it implicitly.
        category_ids: The complete desired set of category ids.

    Raises:
        ValueError: One or more ids in `category_ids` do not exist.
    """
    
    game.categories = await _load_categories(session, category_ids)


class CRUDBoardGame(CRUDBase[BoardGame, BoardGameCreate, BoardGameUpdate]):
    """CRUD operations for board games."""

    async def get_with_categories(
        self,
        session: AsyncSession,
        id: int,
    ) -> BoardGame | None:
        """Fetch a board game with its categories eagerly loaded.

        Args:
            session: Active async session.
            id: Primary key of the board game.

        Returns:
            The row with `categories` populated, or None if no row has that id.
        """
        stmt = (
            select(BoardGame)
            .options(selectinload(BoardGame.categories))
            .where(BoardGame.id == id)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_filtered(
        self,
        session: AsyncSession,
        *,
        players: int | None = None,
        playtime_max: int | None = None,
        category_id: int | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[BoardGame]:
        """List board games matching catalog filters, id-ascending.

        Args:
            session: Active async session.
            players: Keep games whose supported player range includes this
                count. None disables the filter.
            playtime_max: Keep games whose average play time is at most this
                many minutes. None disables the filter.
            category_id: Keep games linked to this category. None disables
                the filter.
            skip: Rows to skip.
            limit: Maximum rows to return.

        Returns:
            Matching rows; empty list if none match.
        """
        stmt = select(BoardGame)

        if players is not None:
            stmt = stmt.where(
                and_(
                    BoardGame.min_players <= players,
                    BoardGame.max_players >= players,
                )
            )
        if playtime_max is not None:
            stmt = stmt.where(BoardGame.playtime_minutes <= playtime_max)
        if category_id is not None:
            stmt = stmt.where(
                BoardGame.categories.any(Category.id == category_id)
            )

        stmt = stmt.order_by(BoardGame.id).offset(skip).limit(limit)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def create_with_categories(
        self,
        session: AsyncSession,
        *,
        data: BoardGameCreate,
    ) -> BoardGame:
        """Insert a board game and link it to the given categories.

        Args:
            session: Active async session.
            data: Validated creation payload, including `category_ids`.

        Returns:
            The flushed row with `categories` populated.

        Raises:
            ValueError: One or more `category_ids` do not exist.
        """
        loaded = await _load_categories(session, data.category_ids)
        payload: dict[str, Any] = data.model_dump(exclude={"category_ids"})
        game = BoardGame(**payload)
        game.categories = loaded
        session.add(game)
        await session.flush()
        return game

    async def update_with_categories(
        self,
        session: AsyncSession,
        *,
        id: int,
        data: BoardGameUpdate,
    ) -> BoardGame | None:
        """Apply a partial update, optionally replacing the category set.

        Args:
            session: Active async session.
            id: Primary key of the board game.
            data: Partial update payload; unset fields are left alone.

        Returns:
            The flushed row with `categories` populated, or None if no row
            has that id.

        Raises:
            ValueError: `category_ids` is present and contains unknown ids.
        """
        game = await self.get_with_categories(session, id)
        if game is None:
            return None

        scalar_updates = data.model_dump(
            exclude_unset=True,
            exclude={"category_ids"},
        )
        for key, value in scalar_updates.items():
            setattr(game, key, value)

        if "category_ids" in data.model_fields_set:
            await set_categories(
                session,
                game,
                data.category_ids or [],
            )

        await session.flush()
        return game


board_game = CRUDBoardGame(BoardGame)