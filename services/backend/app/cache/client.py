"""
Async Redis client bootstrap and FastAPI dependency.

The client is created once at startup and stored on ``app.state``, mirroring
``app.storage.client``. ``redis.asyncio`` is non-blocking, so no thread
dispatch is needed (unlike the sync MinIO SDK).
"""

import logging

import redis.asyncio as redis
from fastapi import FastAPI, Request

from app.config import settings

logger = logging.getLogger(__name__)

_CONNECT_TIMEOUT_SECONDS = 5


def build_redis() -> redis.Redis:
    """Construct an async Redis client from settings. Performs no I/O."""
    return redis.Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=_CONNECT_TIMEOUT_SECONDS,
        socket_timeout=_CONNECT_TIMEOUT_SECONDS,
    )


async def bootstrap_redis(app: FastAPI) -> None:
    """Create the client and ping the server. Called from lifespan.

    Raises on any failure — a backend that cannot reach Redis must not
    start, otherwise refresh-token storage and catalog caching fail at
    request time instead of boot time.
    """
    client = build_redis()
    try:
        await client.ping()
    except Exception as exc:
        await client.aclose()
        logger.exception("Redis unreachable")
        raise RuntimeError(
            f"Cannot reach Redis at {settings.redis_url}"
        ) from exc

    logger.info("Redis client ready: url=%s", settings.redis_url)
    app.state.redis = client


def get_redis(request: Request) -> redis.Redis:
    """FastAPI dependency returning the shared client from app.state."""
    return request.app.state.redis