"""CRUD for employees."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import CRUDBase
from app.db.models import Employee
from app.schemas import EmployeeCreate, EmployeeUpdate


class CRUDEmployee(CRUDBase[Employee, EmployeeCreate, EmployeeUpdate]):
    async def get_by_email(
        self,
        session: AsyncSession,
        email: str,
    ) -> Employee | None:
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
        return obj


employee = CRUDEmployee(Employee)