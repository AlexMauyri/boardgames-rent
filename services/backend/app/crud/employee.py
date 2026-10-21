"""CRUD for employees."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import CRUDBase
from app.db.models import Employee
from app.schemas import EmployeeCreate, EmployeeUpdate


class CRUDEmployee(CRUDBase[Employee, EmployeeCreate, EmployeeUpdate]):
    """CRUD operations for employees."""

    async def get_by_email(
        self,
        session: AsyncSession,
        email: str,
    ) -> Employee | None:
        """Fetch an employee by exact email.

        Args:
            session: Active async session.
            email: Exact, case-sensitive email address.

        Returns:
            The matching employee, or None.
        """
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
        """List employees with a given role, id-ascending.

        Args:
            session: Active async session.
            role: One of COURIER, MANAGER, ADMIN.
            skip: Rows to skip.
            limit: Maximum rows to return.

        Returns:
            Matching rows; empty list if none.
        """
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
        """List employees assigned to a pickup point, id-ascending.

        Args:
            session: Active async session.
            pickup_point_id: Primary key of the pickup point.
            skip: Rows to skip.
            limit: Maximum rows to return.

        Returns:
            Matching rows; empty list if none.
        """
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
        data: EmployeeCreate,
        password_hash: str,
    ) -> Employee:
        """Insert an employee with a pre-computed password hash.

        Args:
            session: Active async session.
            data: Validated creation payload.
            password_hash: Pre-computed argon2 digest.

        Returns:
            The flushed and refreshed employee.
        """
        obj = Employee(
            email=data.email,
            password_hash=password_hash,
            full_name=data.full_name,
            phone=data.phone,
            role=data.role,
            pickup_point_id=data.pickup_point_id,
        )
        session.add(obj)
        await session.flush()
        await session.refresh(obj)
        return obj

    async def activate(
        self,
        session: AsyncSession,
        *,
        id: int,
    ) -> Employee | None:
        """Set `is_active` to True.

        Idempotent. Returns None only when the id does not exist.

        Args:
            session: Active async session.
            id: Primary key of the employee.

        Returns:
            The activated employee, or None if no row has that id.
        """
        obj = await self.get(session, id)
        if obj is None:
            return None
        obj.is_active = True
        await session.flush()
        return obj

    async def deactivate(
        self,
        session: AsyncSession,
        *,
        id: int,
    ) -> Employee | None:
        """Set `is_active` to False.

        Args:
            session: Active async session.
            id: Primary key of the employee.

        Returns:
            The deactivated employee, or None if no row has that id.
        """
        obj = await self.get(session, id)
        if obj is None:
            return None
        obj.is_active = False
        await session.flush()
        return obj


employee = CRUDEmployee(Employee)