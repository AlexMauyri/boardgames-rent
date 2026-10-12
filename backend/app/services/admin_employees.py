"""Employee administration."""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import hash_password
from app.crud import employee, pickup_point
from app.schemas import EmployeeCreate, EmployeeRead, EmployeeUpdate
from app.services.exceptions import ConflictError, NotFoundError


def _is_employee_email_violation(exc: IntegrityError) -> bool:
    """Decide whether an IntegrityError is specifically the email uniqueness violation.

    Args:
        exc: The IntegrityError raised by a flush.

    Returns:
        True only if the violated constraint is `uq_employees_email`.
    """
    orig = getattr(exc, "orig", None)
    if orig is None:
        return "uq_employees_email" in str(exc)

    constraint_name = getattr(orig, "constraint_name", None)
    if constraint_name is None:
        diag = getattr(orig, "diag", None)
        constraint_name = getattr(diag, "constraint_name", None)

    if constraint_name is not None:
        return constraint_name == "uq_employees_email"

    return "uq_employees_email" in str(orig)


async def list_employees(
    session: AsyncSession,
    role: str | None = None,
    skip: int = 0,
    limit: int = 100,
) -> list[EmployeeRead]:
    """List employees, optionally narrowed to a single role.

    Args:
        session: Active async session.
        role: Optional role filter. An unrecognised value yields an empty
            list; validating literals is the schema's job.
        skip: Rows to skip.
        limit: Maximum rows to return.

    Returns:
        Matching rows; empty list if none.
    """
    if role is None:
        rows = await employee.list(session, skip=skip, limit=limit)
    else:
        rows = await employee.list_by_role(session, role, skip=skip, limit=limit)
    return [EmployeeRead.model_validate(row) for row in rows]


async def create_employee(
    session: AsyncSession,
    data: EmployeeCreate,
) -> EmployeeRead:
    """Create an employee account.

    Args:
        session: Active async session.
        data: Validated creation payload; `password` is plaintext.

    Returns:
        The created employee.

    Raises:
        ConflictError: An employee with that email already exists.
    """
    existing = await employee.get_by_email(session, data.email)
    if existing is not None:
        raise ConflictError("Employee", data.email)

    password_hash = hash_password(data.password)

    try:
        obj = await employee.create_with_hash(
            session,
            data=data,
            password_hash=password_hash,
        )
    except IntegrityError as exc:
        await session.rollback()
        if _is_employee_email_violation(exc):
            raise ConflictError("Employee", data.email) from exc
        raise

    result = EmployeeRead.model_validate(obj)
    await session.commit()
    return result


async def update_employee(
    session: AsyncSession,
    employee_id: int,
    data: EmployeeUpdate,
) -> EmployeeRead:
    """Update an employee's profile, role, or assignment.

    Args:
        session: Active async session.
        employee_id: Primary key of the employee.
        data: Partial update payload; unset fields are left alone.

    Returns:
        The updated employee.

    Raises:
        NotFoundError: No employee with that id.
        ValueError: `data` is inconsistent against the current row.
    """
    current = await employee.get(session, employee_id)
    if current is None:
        raise NotFoundError("Employee", employee_id)

    data.validate_against(current)

    obj = await employee.update(
        session,
        id=employee_id,
        data=data.model_dump(exclude_unset=True),
    )
    result = EmployeeRead.model_validate(obj)
    await session.commit()
    return result


async def assign_manager_to_point(
    session: AsyncSession,
    employee_id: int,
    pickup_point_id: int | None,
) -> EmployeeRead:
    """Assign a manager's pickup point.

    Args:
        session: Active async session.
        employee_id: Primary key of the employee. Must have role MANAGER.
        pickup_point_id: The point to assign. Must not be None; clearing is
            not supported through this method.

    Returns:
        The updated employee.

    Raises:
        NotFoundError: No employee with that id, or `pickup_point_id` is
            given but no pickup point with that id exists.
        ValueError: The employee's role is not MANAGER, or `pickup_point_id`
            is None.
    """
    emp = await employee.get(session, employee_id)
    if emp is None:
        raise NotFoundError("Employee", employee_id)

    if emp.role != "MANAGER":
        raise ValueError(
            f"Employee {employee_id} has role {emp.role!r}; "
            "only MANAGER employees can be assigned a pickup point."
        )

    if pickup_point_id is None:
        raise ValueError(
            "Cannot clear pickup_point_id on a MANAGER; "
            "use change_employee_role to change the role first."
        )

    point = await pickup_point.get(session, pickup_point_id)
    if point is None:
        raise NotFoundError("PickupPoint", pickup_point_id)

    emp.pickup_point_id = pickup_point_id
    await session.flush()

    result = EmployeeRead.model_validate(emp)
    await session.commit()
    return result


async def change_employee_role(
    session: AsyncSession,
    employee_id: int,
    new_role: str,
    pickup_point_id: int | None = None,
) -> EmployeeRead:
    """Change an employee's role and pickup-point assignment together.

    Args:
        session: Active async session.
        employee_id: Primary key of the employee.
        new_role: The target role.
        pickup_point_id: The target pickup point, or None. Required to be
            explicit; there is no default inherited from the current row.

    Returns:
        The updated employee.

    Raises:
        NotFoundError: No employee with that id.
        ValueError: The requested (role, pickup_point_id) pairing is invalid.
    """
    emp = await employee.get(session, employee_id)
    if emp is None:
        raise NotFoundError("Employee", employee_id)

    payload = EmployeeUpdate(role=new_role, pickup_point_id=pickup_point_id)
    payload.validate_against(emp)

    obj = await employee.update(
        session,
        id=employee_id,
        data=payload.model_dump(exclude_unset=True),
    )
    result = EmployeeRead.model_validate(obj)
    await session.commit()
    return result