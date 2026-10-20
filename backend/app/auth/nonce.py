"""One-time nonces for DPoP challenges."""

import logging
import secrets

import redis.asyncio as redis

logger = logging.getLogger(__name__)

_NONCE_KEY_PREFIX = "dpop:nonce:"
_NONCE_BYTES = 16
DEFAULT_NONCE_TTL_SECONDS = 60
_MAX_ISSUE_ATTEMPTS = 3


def _key(value: str) -> str:
    """Return the Redis key that stores a nonce value."""
    return f"{_NONCE_KEY_PREFIX}{value}"


async def issue_nonce(
    redis_client: redis.Redis,
    *,
    ttl_seconds: int = DEFAULT_NONCE_TTL_SECONDS,
) -> str:
    """Generate, store, and return a fresh nonce.

    Args:
        redis_client: Redis client.
        ttl_seconds: How long the nonce is valid. RFC 9449 suggests a
            short window so precomputation is not viable.

    Returns:
        The nonce value, ready to be sent in a ``DPoP-Nonce`` header.
    """
    value = secrets.token_hex(_NONCE_BYTES)
    await redis_client.set(_key(value), "1", ex=ttl_seconds)
    logger.debug("issued dpop nonce ttl=%s", ttl_seconds)
    return value


async def consume_nonce(
    redis_client: redis.Redis,
    value: str,
) -> bool:
    """Atomically remove a nonce and report whether it existed.

    Args:
        redis_client: Redis client.
        value: The nonce value from a client's DPoP proof.

    Returns:
        ``True`` if the nonce existed and is now consumed; ``False`` if
        it was never issued, already consumed, or has expired.
    """
    if not value:
        return False
    deleted = await redis_client.getdel(_key(value))
    return deleted is not None