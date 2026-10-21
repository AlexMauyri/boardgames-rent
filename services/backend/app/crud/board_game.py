"""CRUD for board games, plus the M:N link helper."""

from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.crud.base import CRUDBase
from app.db.models import BoardGame, Category


async def _load_categories(
    session: AsyncSession,
    category_ids: list[int],
) -> list[Category]:
    """Load the categories with the given ids, one query, deduplicated."""
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
    """Replace a game's full category set."""
    game.categories = await _load_categories(session, category_ids)


class CRUDBoardGame(CRUDBase[BoardGame]):
    """CRUD operations for board games."""

    async def get_with_categories(
        self,
        session: AsyncSession,
        id: int,
    ) -> BoardGame | None:
        """Fetch a board game with its categories eagerly loaded."""
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
        """List board games matching catalog filters, id-ascending."""
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
        data: dict[str, Any],
        category_ids: list[int],
    ) -> BoardGame:
        """Insert a board game and link it to the given categories.

        Args:
            session: Active async session.
            data: Column values of the game itself (``category_ids`` already
                stripped by the service layer).
            category_ids: The categories to link.

        Returns:
            The flushed row with ``categories`` populated.

        Raises:
            ValueError: ``data`` contains an unknown column, or one or more
                ``category_ids`` do not exist.
        """
        self._validate_columns(data)
        loaded = await _load_categories(session, category_ids)
        game = BoardGame(**data)
        game.categories = loaded
        session.add(game)
        await session.flush()
        return game

    async def update_with_categories(
        self,
        session: AsyncSession,
        *,
        id: int,
        data: dict[str, Any],
        category_ids: list[int] | None,
    ) -> BoardGame | None:
        """Apply a partial update, optionally replacing the category set.

        Args:
            session: Active async session.
            id: Primary key of the board game.
            data: Column values to set (``category_ids`` already stripped).
            category_ids: ``None`` leaves the set untouched; a list (possibly
                empty) replaces the current set.

        Returns:
            The flushed row with ``categories`` populated, or None.

        Raises:
            ValueError: ``data`` contains an unknown column, or ``category_ids``
                contains unknown ids.
        """
        self._validate_columns(data)
        game = await self.get_with_categories(session, id)
        if game is None:
            return None
        for key, value in data.items():
            setattr(game, key, value)
        if category_ids is not None:
            await set_categories(session, game, category_ids)
        await session.flush()
        return game


board_game = CRUDBoardGame(BoardGame)