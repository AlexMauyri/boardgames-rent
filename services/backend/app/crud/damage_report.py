"""CRUD for damage reports."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import CRUDBase
from app.db.models import DamageReport


class CRUDDamageReport(CRUDBase[DamageReport]):
    """CRUD operations for damage reports.

    Reports have no generic update schema: they change only by being
    resolved through the service layer.
    """

    async def get_for_update(
        self,
        session: AsyncSession,
        id: int,
    ) -> DamageReport | None:
        """Fetch a report and lock its row until the transaction ends."""
        stmt = (
            select(DamageReport)
            .where(DamageReport.id == id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def count_open_for_copy(
        self,
        session: AsyncSession,
        copy_id: int,
        *,
        exclude_id: int | None = None,
    ) -> int:
        """Count unresolved reports on a box."""
        stmt = select(func.count()).select_from(DamageReport).where(
            DamageReport.game_copy_id == copy_id,
            DamageReport.resolved_at.is_(None),
        )
        if exclude_id is not None:
            stmt = stmt.where(DamageReport.id != exclude_id)
        return (await session.execute(stmt)).scalar_one()


damage_report = CRUDDamageReport(DamageReport)