"""Admin: staff accounts, roles and manager assignments."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.schemas import EmployeeCreate, EmployeeRead, EmployeeRole, EmployeeUpdate
from app.services import admin_employees

router = APIRouter()


@router.get("", response_model=list[EmployeeRead])
async def list_employees(
    session: Annotated[AsyncSession, Depends(get_session)],
    role: EmployeeRole | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1),
) -> list[EmployeeRead]:
    """List employees, optionally of a single role."""
    return await admin_employees.list_employees(
        session, role=role, skip=skip, limit=limit,
    )


@router.post(
    "",
    response_model=EmployeeRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_employee(
    payload: EmployeeCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> EmployeeRead:
    """Create a staff account. 409 if the email is taken."""
    return await admin_employees.create_employee(session, payload)


@router.put("/{employee_id}", response_model=EmployeeRead)
async def update_employee(
    employee_id: int,
    payload: EmployeeUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> EmployeeRead:
    """Edit an employee's profile; role and point must stay consistent."""
    return await admin_employees.update_employee(session, employee_id, payload)


@router.put("/{employee_id}/role", response_model=EmployeeRead)
async def change_employee_role(
    employee_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    role: EmployeeRole = Query(...),
    pickup_point_id: int | None = Query(None),
) -> EmployeeRead:
    """Change the role; a MANAGER needs `pickup_point_id`, others must omit it."""
    return await admin_employees.change_employee_role(
        session, employee_id, role, pickup_point_id,
    )


@router.put("/{employee_id}/pickup-point", response_model=EmployeeRead)
async def assign_manager_to_point(
    employee_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    pickup_point_id: int = Query(...),
) -> EmployeeRead:
    """Move a manager to another pickup point."""
    return await admin_employees.assign_manager_to_point(
        session, employee_id, pickup_point_id,
    )
