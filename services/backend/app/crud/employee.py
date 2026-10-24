"""CRUD for employees."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import CRUDBase
from app.db.models import Employee


class CRUDEmployee(CRUDBase[Employee]):
    """CRUD operations for employees."""

    async def get_by_email(
        self,
        session: AsyncSession,
        email: str,
    ) -> Employee | None:
        """Fetch an employee by exact email."""
        stmt = select(Employee).where(Employee.email == email)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_role(
        self,
        session: AsyncSession,
        role: str,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Employee]:
        """List employees with a given role, id-ascending."""
        stmt = (
            select(Employee)
            .where(Employee.role == role)
            .order_by(Employee.id)
            .offset(skip)
            .limit(limit)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_pickup_point(
        self,
        session: AsyncSession,
        pickup_point_id: int,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Employee]:
        """List employees assigned to a pickup point, id-ascending."""
        stmt = (
            select(Employee)
            .where(Employee.pickup_point_id == pickup_point_id)
            .order_by(Employee.id)
            .offset(skip)
            .limit(limit)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def create_with_hash(
        self,
        session: AsyncSession,
        *,
        data: dict[str, Any],
        password_hash: str,
    ) -> Employee:
        """Insert an employee with a pre-computed password hash.

        Args:
            session: Active async session.
            data: Column values of the employee (without ``password``).
            password_hash: Pre-computed argon2 digest.

        Returns:
            The flushed and refreshed employee.

        Raises:
            ValueError: ``data`` contains an unknown column.
        """
        payload = {**data, "password_hash": password_hash}
        self._validate_columns(payload)
        obj = Employee(**payload)
        session.add(obj)
        await session.flush()
        await session.refresh(obj)
        return obj

    async def activate(self, session: AsyncSession, *, id: int) -> Employee | None:
        """Set ``is_active`` to True."""
        obj = await self.get(session, id)
        if obj is None:
            return None
        obj.is_active = True
        await session.flush()
        return obj

    async def deactivate(self, session: AsyncSession, *, id: int) -> Employee | None:
        """Set ``is_active`` to False."""
        obj = await self.get(session, id)
        if obj is None:
            return None
        obj.is_active = False
        await session.flush()
        return obj


employee = CRUDEmployee(Employee)