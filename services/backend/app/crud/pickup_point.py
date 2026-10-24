"""CRUD for pickup points."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import CRUDBase
from app.db.models import PickupPoint


class CRUDPickupPoint(CRUDBase[PickupPoint]):
    """CRUD operations for pickup points."""

    async def get_by_name(
        self,
        session: AsyncSession,
        name: str,
    ) -> PickupPoint | None:
        """Fetch a pickup point by exact name."""
        stmt = select(PickupPoint).where(PickupPoint.name == name)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_active(
        self,
        session: AsyncSession,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> list[PickupPoint]:
        """List pickup points flagged active, id-ascending."""
        stmt = (
            select(PickupPoint)
            .where(PickupPoint.is_active.is_(True))
            .order_by(PickupPoint.id)
            .offset(skip)
            .limit(limit)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def activate(self, session: AsyncSession, *, id: int) -> PickupPoint | None:
        """Set ``is_active`` to True."""
        obj = await self.get(session, id)
        if obj is None:
            return None
        obj.is_active = True
        await session.flush()
        return obj

    async def deactivate(self, session: AsyncSession, *, id: int) -> PickupPoint | None:
        """Set ``is_active`` to False."""
        obj = await self.get(session, id)
        if obj is None:
            return None
        obj.is_active = False
        await session.flush()
        return obj


pickup_point = CRUDPickupPoint(PickupPoint)