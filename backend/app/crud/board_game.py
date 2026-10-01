"""CRUD for board games, plus the M:N link helper."""

from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.crud.base import CRUDBase
from app.db.models import BoardGame, Category
from app.schemas import BoardGameCreate, BoardGameUpdate


async def set_board_game_categories(
    session: AsyncSession,
    game: BoardGame,
    category_ids: list[int],
) -> None:
    unique_ids = set(category_ids)
    if not unique_ids:
        game.categories = []
        return

    stmt = select(Category).where(Category.id.in_(unique_ids))
    result = await session.execute(stmt)
    loaded = list(result.scalars().all())

    if len(loaded) != len(unique_ids):
        found = {c.id for c in loaded}
        missing = sorted(unique_ids - found)
        raise ValueError(f"Unknown category ids: {missing}")

    game.categories = loaded


class CRUDBoardGame(CRUDBase[BoardGame, BoardGameCreate, BoardGameUpdate]):
    async def get_with_categories(
        self,
        session: AsyncSession,
        id: int,
    ) -> BoardGame | None:
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
        payload: dict[str, Any] = data.model_dump(exclude={"category_ids"})
        game = BoardGame(**payload)
        session.add(game)
        await session.flush()

        await set_board_game_categories(session, game, data.category_ids)
        await session.flush()
        return game

    async def update_with_categories(
        self,
        session: AsyncSession,
        *,
        id: int,
        data: BoardGameUpdate,
    ) -> BoardGame | None:
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
            await set_board_game_categories(
                session,
                game,
                data.category_ids or [],
            )

        await session.flush()
        return game


board_game = CRUDBoardGame(BoardGame)