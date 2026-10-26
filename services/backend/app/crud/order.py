"""CRUD for orders."""

from collections.abc import Collection
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.crud.base import CRUDBase
from app.db.models import GameCopy, Order, OrderItem

OPEN_STATUSES = (
    "CREATED",
    "NEEDS_TRANSFER",
    "IN_TRANSIT",
    "READY_FOR_PICKUP",
    "ACTIVE",
)


class CRUDOrder(CRUDBase[Order]):
    """CRUD operations for orders.

    Orders have no generic update schema: their fields change only through
    the status transitions of the service layer.
    """

    async def get_detail(
        self,
        session: AsyncSession,
        id: int,
    ) -> Order | None:
        """Fetch an order with its lines eagerly loaded and freshly read."""
        stmt = (
            select(Order)
            .options(selectinload(Order.items))
            .where(Order.id == id)
            .execution_options(populate_existing=True)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_for_update(
        self,
        session: AsyncSession,
        id: int,
    ) -> Order | None:
        """Fetch an order and lock its row until the transaction ends."""
        stmt = (
            select(Order)
            .where(Order.id == id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_client(
        self,
        session: AsyncSession,
        client_id: int,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Order]:
        """List a client's orders, newest first."""
        stmt = (
            select(Order)
            .where(Order.client_id == client_id)
            .order_by(Order.id.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_point(
        self,
        session: AsyncSession,
        point_id: int,
        *,
        status: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Order]:
        """List orders collected at a pickup point, newest first."""
        stmt = select(Order).where(Order.pickup_point_id == point_id)
        if status is not None:
            stmt = stmt.where(Order.status == status)
        stmt = stmt.order_by(Order.id.desc()).offset(skip).limit(limit)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def busy_copy_ids(
        self,
        session: AsyncSession,
        copy_ids: Collection[int],
    ) -> set[int]:
        """Find which of the given boxes already belong to an open order."""
        if not copy_ids:
            return set()
        stmt = (
            select(OrderItem.game_copy_id)
            .join(Order, Order.id == OrderItem.order_id)
            .where(
                OrderItem.game_copy_id.in_(set(copy_ids)),
                Order.status.in_(OPEN_STATUSES),
            )
        )
        result = await session.execute(stmt)
        return set(result.scalars().all())

    async def create_with_items(
        self,
        session: AsyncSession,
        *,
        values: dict[str, Any],
        items: list[tuple[int, Decimal]],
    ) -> Order:
        """Insert an order together with its lines in one flush."""
        self._validate_columns(values)
        obj = Order(**values)
        obj.items = [
            OrderItem(game_copy_id=copy_id, price_at_rental=price)
            for copy_id, price in items
        ]
        session.add(obj)
        await session.flush()
        return obj

    async def get_active_game_ids(
        self,
        session: AsyncSession,
        client_id: int,
    ) -> list[int]:
        """Return distinct catalog game ids from the client's open orders."""
        stmt = (
            select(GameCopy.game_id)
            .distinct()
            .join(OrderItem, OrderItem.game_copy_id == GameCopy.id)
            .join(Order, Order.id == OrderItem.order_id)
            .where(
                Order.client_id == client_id,
                Order.status.in_(OPEN_STATUSES),
            )
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())


order = CRUDOrder(Order)