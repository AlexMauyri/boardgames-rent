"""Authentication router: register, login, refresh, logout."""

from typing import Annotated

import redis.asyncio as redis
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_redis, get_session
from app.auth.jwt import InvalidTokenError
from app.schemas import (
    ClientCreate,
    ClientRead,
    LoginRequest,
    RefreshRequest,
    TokenPair,
)
from app.services import auth as auth_service
from app.services import tokens as tokens_service

router = APIRouter()


def _invalid_credentials() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


@router.post(
    "/register/client",
    response_model=ClientRead,
    status_code=status.HTTP_201_CREATED,
)
async def register_client(
    payload: ClientCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ClientRead:
    """Register a new client account."""
    return await auth_service.register_client(session, payload)


@router.post("/login/client", response_model=TokenPair)
async def login_client(
    payload: LoginRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    redis_client: Annotated[redis.Redis, Depends(get_redis)],
) -> TokenPair:
    """Verify client credentials and issue a token pair."""
    user = await auth_service.authenticate_client(
        session, payload.email, payload.password,
    )
    if user is None:
        raise _invalid_credentials()
    return await tokens_service.issue_pair(redis_client, user.id, "CLIENT")


@router.post("/login/employee", response_model=TokenPair)
async def login_employee(
    payload: LoginRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    redis_client: Annotated[redis.Redis, Depends(get_redis)],
) -> TokenPair:
    """Verify employee credentials and issue a token pair."""
    user = await auth_service.authenticate_employee(
        session, payload.email, payload.password,
    )
    if user is None:
        raise _invalid_credentials()
    return await tokens_service.issue_pair(redis_client, user.id, user.role)


@router.post("/refresh", response_model=TokenPair)
async def refresh(
    payload: RefreshRequest,
    redis_client: Annotated[redis.Redis, Depends(get_redis)],
) -> TokenPair:
    """Rotate a refresh token into a fresh access + refresh pair."""
    return await tokens_service.rotate(redis_client, payload.refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    payload: RefreshRequest,
    redis_client: Annotated[redis.Redis, Depends(get_redis)],
) -> None:
    """Revoke a refresh token. A malformed token is not an error here."""
    try:
        await tokens_service.revoke(redis_client, payload.refresh_token)
    except InvalidTokenError:
        pass