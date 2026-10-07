"""CRUD for physical game boxes."""

from collections.abc import Collection

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import CRUDBase
from app.db.models import GameCopy, OrderItem
from app.schemas import GameCopyCreate, GameCopyUpdate


class CRUDGameCopy(CRUDBase[GameCopy, GameCopyCreate, GameCopyUpdate]):
    """CRUD operations for game copies."""

    async def get_by_inventory_number(
        self,
        session: AsyncSession,
        inventory_number: str,
    ) -> GameCopy | None:
        """Fetch a copy by its barcode label.

        Args:
            session: Active async session.
            inventory_number: Exact inventory number.

        Returns:
            The matching copy, or None.
        """
        stmt = select(GameCopy).where(
            GameCopy.inventory_number == inventory_number
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_available_for_games(
        self,
        session: AsyncSession,
        game_ids: Collection[int],
        *,
        lock: bool = False,
    ) -> list[GameCopy]:
        """List boxes of the given games that are physically on a shelf.

        Args:
            session: Active async session.
            game_ids: Catalog games to look for.
            lock: When True, `SELECT ... FOR UPDATE` the rows (in id order, so
                concurrent callers cannot deadlock) until the transaction ends.

        Returns:
            Copies with status AVAILABLE, id-ascending; empty if none.
        """
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

    async def list_for_order(
        self,
        session: AsyncSession,
        order_id: int,
        *,
        lock: bool = False,
    ) -> list[GameCopy]:
        """List the boxes included in an order.

        Args:
            session: Active async session.
            order_id: Primary key of the order.
            lock: When True, lock the copy rows until the transaction ends.

        Returns:
            The order's copies, id-ascending; empty if none.
        """
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
