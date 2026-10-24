"""CRUD for categories."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import CRUDBase
from app.db.models import Category


class CRUDCategory(CRUDBase[Category]):
    """CRUD operations for categories."""

    async def get_by_name(
        self,
        session: AsyncSession,
        name: str,
    ) -> Category | None:
        """Fetch a category by exact name."""
        stmt = select(Category).where(Category.name == name)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()


category = CRUDCategory(Category)