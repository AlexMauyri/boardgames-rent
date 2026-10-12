"""Client registration and credential verification."""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import DUMMY_HASH, hash_password, verify_password
from app.crud import client, employee
from app.schemas import ClientCreate, ClientRead, EmployeeRead
from app.services.exceptions import ConflictError


def _is_client_email_violation(exc: IntegrityError) -> bool:
    """Decide whether an IntegrityError is specifically the email uniqueness violation.

    Args:
        exc: The IntegrityError raised by a flush.

    Returns:
        True only if the violated constraint is `uq_clients_email`.
    """
    orig = getattr(exc, "orig", None)
    if orig is None:
        return "uq_clients_email" in str(exc)

    constraint_name = getattr(orig, "constraint_name", None)
    if constraint_name is None:
        diag = getattr(orig, "diag", None)
        constraint_name = getattr(diag, "constraint_name", None)

    if constraint_name is not None:
        return constraint_name == "uq_clients_email"

    return "uq_clients_email" in str(orig)


async def register_client(
    session: AsyncSession,
    data: ClientCreate,
) -> ClientRead:
    """Register a new client account.

    Args:
        session: Active async session.
        data: Validated registration payload; `password` is plaintext.

    Returns:
        The created client.

    Raises:
        ConflictError: An account with that email already exists.
    """
    existing = await client.get_by_email(session, data.email)
    if existing is not None:
        raise ConflictError("Client", data.email)

    password_hash = hash_password(data.password)

    try:
        obj = await client.create_with_hash(
            session,
            data=data,
            password_hash=password_hash,
        )
    except IntegrityError as exc:
        await session.rollback()
        if _is_client_email_violation(exc):
            raise ConflictError("Client", data.email) from exc
        raise

    result = ClientRead.model_validate(obj)
    await session.commit()
    return result


async def authenticate_client(
    session: AsyncSession,
    email: str,
    password: str,
) -> ClientRead | None:
    """Verify a client's credentials.

    Args:
        session: Active async session.
        email: Email address as submitted.
        password: Plaintext password as submitted.

    Returns:
        The authenticated client, or None for an unknown email, a wrong
        password, or a disabled account — the three are not distinguished.
    """
    row = await client.get_by_email(session, email)

    if row is None:
        verify_password(password, DUMMY_HASH)
        return None

    if not verify_password(password, row.password_hash):
        return None

    if not row.is_active:
        return None

    return ClientRead.model_validate(row)


async def authenticate_employee(
    session: AsyncSession,
    email: str,
    password: str,
) -> EmployeeRead | None:
    """Verify an employee's credentials.

    Args:
        session: Active async session.
        email: Email address as submitted.
        password: Plaintext password as submitted.

    Returns:
        The authenticated employee, or None for an unknown email, a wrong
        password, or a disabled account — the three are not distinguished.
    """
    row = await employee.get_by_email(session, email)

    if row is None:
        verify_password(password, DUMMY_HASH)
        return None

    if not verify_password(password, row.password_hash):
        return None

    if not row.is_active:
        return None

    return EmployeeRead.model_validate(row)