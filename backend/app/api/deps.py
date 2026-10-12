"""FastAPI dependencies: authentication, roles, shared clients."""

from typing import Annotated, NamedTuple

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import InvalidTokenError, decode_access_token
from app.cache.client import get_redis
from app.crud import client as client_crud
from app.crud import employee as employee_crud
from app.db.models import Client, Employee
from app.db.session import get_session
from app.storage.client import get_storage_client

_bearer = HTTPBearer(auto_error=False)

_EMPLOYEE_ROLES = ("COURIER", "MANAGER", "ADMIN")


class Principal(NamedTuple):
    """Identity extracted from a valid access token."""

    id: int
    role: str


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_principal(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(_bearer)
    ],
) -> Principal:
    """Decode the Bearer token and return the caller's identity.

    Raises:
        HTTPException: 401 when the header is missing or the token is not
            a valid, unexpired access token.
    """
    if credentials is None or not credentials.credentials:
        raise _unauthorized("Missing bearer token")

    try:
        claims = decode_access_token(credentials.credentials)
    except InvalidTokenError as exc:
        raise _unauthorized("Invalid or expired token") from exc

    try:
        user_id = int(claims["sub"])
    except (KeyError, TypeError, ValueError) as exc:
        raise _unauthorized("Malformed token subject") from exc

    role = claims.get("role")
    if not isinstance(role, str) or not role:
        raise _unauthorized("Malformed token role")

    return Principal(id=user_id, role=role)


async def get_current_client(
    principal: Annotated[Principal, Depends(get_current_principal)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Client:
    """Resolve the caller as an active client, or raise 401."""
    if principal.role != "CLIENT":
        raise _unauthorized("Not a client token")
    row = await client_crud.get(session, principal.id)
    if row is None or not row.is_active:
        raise _unauthorized("Client not found or inactive")
    return row


async def get_current_employee(
    principal: Annotated[Principal, Depends(get_current_principal)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Employee:
    """Resolve the caller as an active employee, or raise 401."""
    if principal.role not in _EMPLOYEE_ROLES:
        raise _unauthorized("Not an employee token")
    row = await employee_crud.get(session, principal.id)
    if row is None or not row.is_active:
        raise _unauthorized("Employee not found or inactive")
    return row


def require_role(*roles: str):
    """Build a dependency that requires an active employee with one of `roles`.

    A valid token with a wrong role yields 403. A valid token whose subject
    no longer exists or is deactivated yields 401, matching `get_current_employee`.
    """

    async def _dep(
        principal: Annotated[Principal, Depends(get_current_principal)],
        session: Annotated[AsyncSession, Depends(get_session)],
    ) -> Employee:
        if principal.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of roles: {', '.join(roles)}",
            )
        row = await employee_crud.get(session, principal.id)
        if row is None or not row.is_active:
            raise _unauthorized("Employee not found or inactive")
        return row

    return _dep


__all__ = [
    "Principal",
    "get_current_principal",
    "get_current_client",
    "get_current_employee",
    "require_role",
    "get_session",
    "get_redis",
    "get_storage_client",
]