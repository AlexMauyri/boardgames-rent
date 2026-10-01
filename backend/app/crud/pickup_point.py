"""CRUD for pickup points."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import CRUDBase
from app.db.models import PickupPoint
from app.schemas import PickupPointCreate, PickupPointUpdate


class CRUDPickupPoint(CRUDBase[PickupPoint, PickupPointCreate, PickupPointUpdate]):
    async def list_active(
        self,
        session: AsyncSession,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> list[PickupPoint]:
        stmt = (
            select(PickupPoint)
            .where(PickupPoint.is_active.is_(True))
            .order_by(PickupPoint.id)
            .offset(skip)
            .limit(limit)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def deactivate(
        self,
        session: AsyncSession,
        *,
        id: int,
    ) -> PickupPoint | None:
        obj = await self.get(session, id)
        if obj is None:
            return None
        obj.is_active = False
        await session.flush()
        return obj


pickup_point = CRUDPickupPoint(PickupPoint)