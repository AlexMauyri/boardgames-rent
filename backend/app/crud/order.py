"""CRUD for orders."""

from collections.abc import Collection
from decimal import Decimal
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.crud.base import CRUDBase
from app.db.models import Order, OrderItem
from app.schemas import OrderCreate

# Statuses in which an order still holds its boxes.
OPEN_STATUSES = (
    "CREATED",
    "NEEDS_TRANSFER",
    "IN_TRANSIT",
    "READY_FOR_PICKUP",
    "ACTIVE",
)


class CRUDOrder(CRUDBase[Order, OrderCreate, BaseModel]):
    """CRUD operations for orders.

    Orders have no generic update schema: their fields change only through
    the status transitions of the service layer.
    """

    async def get_detail(
        self,
        session: AsyncSession,
        id: int,
    ) -> Order | None:
        """Fetch an order with its lines eagerly loaded and freshly read.

        Args:
            session: Active async session.
            id: Primary key of the order.

        Returns:
            The order with `items` populated, or None if no row has that id.
        """
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
        """Fetch an order and lock its row until the transaction ends.

        Args:
            session: Active async session.
            id: Primary key of the order.

        Returns:
            The freshly read order, or None if no row has that id.
        """
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
        """List a client's orders, newest first.

        Args:
            session: Active async session.
            client_id: Primary key of the client.
            skip: Rows to skip.
            limit: Maximum rows to return.

        Returns:
            Matching orders without their lines; empty list if none.
        """
        stmt = (
            select(Order)
            .where(Order.client_id == client_id)
            .order_by(Order.id.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def busy_copy_ids(
        self,
        session: AsyncSession,
        copy_ids: Collection[int],
    ) -> set[int]:
        """Find which of the given boxes already belong to an open order.

        Args:
            session: Active async session.
            copy_ids: Candidate game copy ids.

        Returns:
            The subset held by an order in an open status.
        """
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
        """Insert an order together with its lines in one flush.

        Args:
            session: Active async session.
            values: Column values of the order itself.
            items: `(game_copy_id, price_at_rental)` pairs, one per box.

        Returns:
            The flushed order. Server-generated columns are not yet loaded;
            re-read it with `get_detail` before serialising.
        """
        obj = Order(**values)
        obj.items = [
            OrderItem(game_copy_id=copy_id, price_at_rental=price)
            for copy_id, price in items
        ]
        session.add(obj)
        await session.flush()
        return obj


order = CRUDOrder(Order)
