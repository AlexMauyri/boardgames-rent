"""CRUD for physical game boxes."""

from collections.abc import Collection

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import CRUDBase
from app.crud.order import OPEN_STATUSES
from app.db.models import GameCopy, Order, OrderItem


class CRUDGameCopy(CRUDBase[GameCopy]):
    """CRUD operations for game copies."""

    async def get_by_inventory_number(
        self,
        session: AsyncSession,
        inventory_number: str,
    ) -> GameCopy | None:
        """Fetch a copy by its barcode label."""
        stmt = select(GameCopy).where(
            GameCopy.inventory_number == inventory_number
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_for_update(
        self,
        session: AsyncSession,
        id: int,
    ) -> GameCopy | None:
        """Fetch a copy and lock its row until the transaction ends."""
        stmt = (
            select(GameCopy)
            .where(GameCopy.id == id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_filtered(
        self,
        session: AsyncSession,
        *,
        game_id: int | None = None,
        point_id: int | None = None,
        status: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[GameCopy]:
        """List copies matching the given filters, id-ascending."""
        stmt = select(GameCopy)
        if game_id is not None:
            stmt = stmt.where(GameCopy.game_id == game_id)
        if point_id is not None:
            stmt = stmt.where(GameCopy.current_point_id == point_id)
        if status is not None:
            stmt = stmt.where(GameCopy.status == status)
        stmt = stmt.order_by(GameCopy.id).offset(skip).limit(limit)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def list_available_for_games(
        self,
        session: AsyncSession,
        game_ids: Collection[int],
        *,
        lock: bool = False,
    ) -> list[GameCopy]:
        """List boxes of the given games that are physically on a shelf."""
        if not game_ids:
            return []
        stmt = (
            select(GameCopy)
            .where(
                GameCopy.game_id.in_(set(game_ids)),
                GameCopy.status == "AVAILABLE",
            )
            .order_by(GameCopy.id)
            .execution_options(populate_existing=True)
        )
        if lock:
            stmt = stmt.with_for_update()
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def count_free(
        self,
        session: AsyncSession,
        game_ids: Collection[int],
    ) -> dict[tuple[int, int], int]:
        """Count free boxes per game and pickup point."""
        if not game_ids:
            return {}
        held = (
            select(OrderItem.game_copy_id)
            .join(Order, Order.id == OrderItem.order_id)
            .where(Order.status.in_(OPEN_STATUSES))
        )
        stmt = (
            select(GameCopy.game_id, GameCopy.current_point_id, func.count())
            .where(
                GameCopy.game_id.in_(set(game_ids)),
                GameCopy.status == "AVAILABLE",
                GameCopy.id.not_in(held),
            )
            .group_by(GameCopy.game_id, GameCopy.current_point_id)
        )
        result = await session.execute(stmt)
        return {(g, p): n for g, p, n in result.all()}

    async def list_for_order(
        self,
        session: AsyncSession,
        order_id: int,
        *,
        lock: bool = False,
    ) -> list[GameCopy]:
        """List the boxes included in an order."""
        stmt = (
            select(GameCopy)
            .join(OrderItem, OrderItem.game_copy_id == GameCopy.id)
            .where(OrderItem.order_id == order_id)
            .order_by(GameCopy.id)
            .execution_options(populate_existing=True)
        )
        if lock:
            stmt = stmt.with_for_update(of=GameCopy)
        result = await session.execute(stmt)
        return list(result.scalars().all())


game_copy = CRUDGameCopy(GameCopy)