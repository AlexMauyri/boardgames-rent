"""Refresh-token service backed by Redis.

Access tokens are stateless; refresh tokens are valid only while their
``jti`` is registered in Redis. Logout and rotation both delete that key.
The service takes the Redis client as an argument — no FastAPI or app.state
imports live here.
"""

import json

import redis.asyncio as redis

from app.auth.jwt import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    InvalidTokenError,
)
from app.config import settings
from app.schemas import TokenPair

_KEY_PREFIX = "refresh:"


def _key(jti: str) -> str:
    """Return the Redis key that stores a refresh token's jti."""
    return f"{_KEY_PREFIX}{jti}"


async def issue_pair(
    redis_client: redis.Redis,
    user_id: int,
    role: str,
) -> TokenPair:
    """Issue a fresh access + refresh pair and register the refresh jti.

    Args:
        redis_client: Active async Redis client.
        user_id: Subject id — a client or employee primary key.
        role: "CLIENT" or an employee role.

    Returns:
        The newly signed pair.
    """
    access = create_access_token(user_id, role)
    refresh, jti = create_refresh_token(user_id, role)

    await redis_client.set(
        _key(jti),
        json.dumps({"user_id": user_id, "role": role}),
        ex=settings.refresh_token_ttl,
    )

    return TokenPair(access_token=access, refresh_token=refresh)


async def rotate(
    redis_client: redis.Redis,
    refresh_token: str,
) -> TokenPair:
    """Exchange a valid refresh token for a new pair (rotation).

    The old jti is deleted before the new pair is issued, so a leaked
    refresh token can be used at most once.

    Args:
        redis_client: Active async Redis client.
        refresh_token: The token to consume.

    Returns:
        A new access + refresh pair.

    Raises:
        InvalidTokenError: The token is malformed, expired, of the wrong
            type, or its jti is no longer registered (revoked or already
            rotated).
    """
    claims = decode_refresh_token(refresh_token)
    jti = claims["jti"]

    deleted = await redis_client.delete(_key(jti))
    if deleted == 0:
        raise InvalidTokenError("revoked")

    user_id = int(claims["sub"])
    role = claims["role"]
    return await issue_pair(redis_client, user_id, role)


async def revoke(
    redis_client: redis.Redis,
    refresh_token: str,
) -> None:
    """Delete a refresh token's jti. Idempotent.

    Args:
        redis_client: Active async Redis client.
        refresh_token: The token to revoke.

    Raises:
        InvalidTokenError: The token is malformed, expired, or of the
            wrong type. A token whose jti is already gone is not an error.
    """
    claims = decode_refresh_token(refresh_token)
    await redis_client.delete(_key(claims["jti"]))