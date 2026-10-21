"""CRUD for courier deliveries."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import CRUDBase
from app.db.models import Delivery


class CRUDDelivery(CRUDBase[Delivery]):
    """CRUD operations for deliveries.

    Deliveries have no generic update schema: their fields change only
    through the status transitions of the service layer.
    """

    async def get_for_update(
        self,
        session: AsyncSession,
        id: int,
    ) -> Delivery | None:
        """Fetch a delivery and lock its row until the transaction ends."""
        stmt = (
            select(Delivery)
            .where(Delivery.id == id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_order(
        self,
        session: AsyncSession,
        order_id: int,
        *,
        for_update: bool = False,
    ) -> Delivery | None:
        """Fetch the delivery serving an order."""
        stmt = (
            select(Delivery)
            .where(Delivery.order_id == order_id)
            .execution_options(populate_existing=True)
        )
        if for_update:
            stmt = stmt.with_for_update()
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_open(
        self,
        session: AsyncSession,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Delivery]:
        """List tasks no courier has accepted yet, oldest first."""
        stmt = (
            select(Delivery)
            .where(
                Delivery.status == "CREATED",
                Delivery.courier_id.is_(None),
            )
            .order_by(Delivery.id)
            .offset(skip)
            .limit(limit)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_courier(
        self,
        session: AsyncSession,
        courier_id: int,
        *,
        active_only: bool = True,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Delivery]:
        """List a courier's tasks, oldest first."""
        stmt = select(Delivery).where(Delivery.courier_id == courier_id)
        if active_only:
            stmt = stmt.where(Delivery.status.in_(("ACCEPTED", "IN_TRANSIT")))
        stmt = stmt.order_by(Delivery.id).offset(skip).limit(limit)
        result = await session.execute(stmt)
        return list(result.scalars().all())


delivery = CRUDDelivery(Delivery)