"""Authentication router: register, login, refresh, logout."""

from typing import Annotated

import redis.asyncio as redis
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_redis, get_session
from app.auth.dpop import DpopNonceRequired, verify_dpop_proof
from app.auth.jwt import InvalidTokenError
from app.config import settings
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
        headers={"WWW-Authenticate": "DPoP"},
    )


def _missing_proof() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing DPoP proof",
        headers={"WWW-Authenticate": 'DPoP error="invalid_dpop_proof"'},
    )


async def _verify_auth_dpop(
    request: Request,
    redis_client: redis.Redis,
) -> str:
    """Verify a DPoP proof on an auth endpoint and return its thumbprint.

    Raises:
        HTTPException: 401 when the proof is missing. DPoP-specific
            errors (``DpopInvalidProof``, ``DpopExpired``,
            ``DpopReplay``, ``DpopNonceRequired``) propagate and are
            mapped by ``app.api.errors``.
    """
    proof = request.headers.get("dpop")
    if not proof:
        raise _missing_proof()

    htu = str(request.url.replace(query="", fragment=""))
    return await verify_dpop_proof(
        proof,
        expected_htm=request.method,
        expected_htu=htu,
        expected_jkt=None,
        redis_client=redis_client,
        require_nonce=settings.dpop_require_nonce,
        iat_window_seconds=settings.dpop_iat_window_seconds,
        jti_ttl_seconds=settings.dpop_jti_ttl_seconds,
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
    """Register a new client account. No DPoP: nothing secret is issued."""
    return await auth_service.register_client(session, payload)


@router.post("/login/client", response_model=TokenPair)
async def login_client(
    payload: LoginRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    redis_client: Annotated[redis.Redis, Depends(get_redis)],
) -> TokenPair:
    """Verify client credentials and issue a DPoP-bound pair.

    DPoP is checked before the password, so brute-force attempts must
    also produce a valid proof.
    """
    jkt = await _verify_auth_dpop(request, redis_client)

    user = await auth_service.authenticate_client(
        session, payload.email, payload.password,
    )
    if user is None:
        raise _invalid_credentials()

    return await tokens_service.issue_pair(
        redis_client, user.id, "CLIENT", cnf_jkt=jkt,
    )


@router.post("/login/employee", response_model=TokenPair)
async def login_employee(
    payload: LoginRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    redis_client: Annotated[redis.Redis, Depends(get_redis)],
) -> TokenPair:
    """Verify employee credentials and issue a DPoP-bound pair."""
    jkt = await _verify_auth_dpop(request, redis_client)

    user = await auth_service.authenticate_employee(
        session, payload.email, payload.password,
    )
    if user is None:
        raise _invalid_credentials()

    return await tokens_service.issue_pair(
        redis_client, user.id, user.role, cnf_jkt=jkt,
    )


@router.post("/refresh", response_model=TokenPair)
async def refresh(
    payload: RefreshRequest,
    request: Request,
    redis_client: Annotated[redis.Redis, Depends(get_redis)],
) -> TokenPair:
    """Rotate a refresh token into a fresh DPoP-bound pair."""
    jkt = await _verify_auth_dpop(request, redis_client)
    return await tokens_service.rotate(
        redis_client, payload.refresh_token, proof_jkt=jkt,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    payload: RefreshRequest,
    request: Request,
    redis_client: Annotated[redis.Redis, Depends(get_redis)],
) -> None:
    """Revoke a refresh token. A malformed or already-revoked token is
    not an error: the caller ends up logged out either way."""
    jkt = await _verify_auth_dpop(request, redis_client)
    try:
        await tokens_service.revoke(
            redis_client, payload.refresh_token, proof_jkt=jkt,
        )
    except InvalidTokenError:
        pass