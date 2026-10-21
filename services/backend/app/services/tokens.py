"""Refresh-token service backed by Redis, bound to DPoP keys."""

import json
import logging

import redis.asyncio as redis

from app.auth.jwt import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    InvalidTokenError,
)
from app.config import settings
from app.schemas import TokenPair

logger = logging.getLogger(__name__)

_KEY_PREFIX = "refresh:"
_JTI_PREFIX_LEN = 8


def _key(jti: str) -> str:
    """Return the Redis key that stores a refresh token's jti."""
    return f"{_KEY_PREFIX}{jti}"


def _prefix(jti: str) -> str:
    """First characters of a jti, for log output."""
    return jti[:_JTI_PREFIX_LEN]


async def issue_pair(
    redis_client: redis.Redis,
    user_id: int,
    role: str,
    *,
    cnf_jkt: str,
) -> TokenPair:
    """Issue a fresh access + refresh pair, binding the refresh to a key.

    Args:
        redis_client: Active async Redis client.
        user_id: Subject id — a client or employee primary key.
        role: "CLIENT" or an employee role.
        cnf_jkt: JWK thumbprint of the client's DPoP key. Stored both in
            the refresh token's ``cnf.jkt`` and in the Redis record.

    Returns:
        The newly signed pair. ``token_type`` is ``"DPoP"``.
    """
    access = create_access_token(user_id, role)
    refresh, jti = create_refresh_token(user_id, role, cnf_jkt=cnf_jkt)

    await redis_client.set(
        _key(jti),
        json.dumps({"user_id": user_id, "role": role, "jkt": cnf_jkt}),
        ex=settings.refresh_token_ttl,
    )

    logger.info(
        "tokens issued user_id=%s role=%s jti_prefix=%s",
        user_id, role, _prefix(jti),
    )
    return TokenPair(access_token=access, refresh_token=refresh)


def _extract_cnf_jkt(claims: dict) -> str:
    """Pull ``cnf.jkt`` out of a decoded refresh token.

    Raises:
        InvalidTokenError: The claim is missing or malformed. A token
            without ``cnf.jkt`` was issued before DPoP binding existed
            and can no longer be used; the client must log in again.
    """
    cnf = claims.get("cnf")
    if not isinstance(cnf, dict):
        raise InvalidTokenError("missing cnf")
    jkt = cnf.get("jkt")
    if not isinstance(jkt, str) or not jkt:
        raise InvalidTokenError("missing cnf.jkt")
    return jkt


async def rotate(
    redis_client: redis.Redis,
    refresh_token: str,
    *,
    proof_jkt: str,
) -> TokenPair:
    """Exchange a valid refresh token for a new pair (rotation).

    Args:
        redis_client: Active async Redis client.
        refresh_token: The token to consume.
        proof_jkt: Thumbprint of the key that signed this request's DPoP
            proof. Computed by ``verify_dpop_proof``.

    Returns:
        A new access + refresh pair, bound to the same ``jkt``.

    Raises:
        InvalidTokenError: The token is malformed, expired, of the wrong
            type, missing ``cnf.jkt``, its ``cnf.jkt`` differs from the
            proof's, the Redis record's ``jkt`` differs from the proof's,
            or the jti is no longer registered (revoked or already
            rotated).
    """
    claims = decode_refresh_token(refresh_token)
    jti = claims["jti"]
    token_jkt = _extract_cnf_jkt(claims)

    if token_jkt != proof_jkt:
        logger.warning(
            "refresh rotation rejected jti_prefix=%s reason=jkt_mismatch",
            _prefix(jti),
        )
        raise InvalidTokenError("jkt_mismatch")

    raw = await redis_client.getdel(_key(jti))
    if raw is None:
        logger.warning(
            "refresh rotation rejected jti_prefix=%s reason=revoked",
            _prefix(jti),
        )
        raise InvalidTokenError("revoked")

    stored = json.loads(raw)
    if stored.get("jkt") != proof_jkt:
        logger.warning(
            "refresh rotation rejected jti_prefix=%s reason=stored_jkt_mismatch",
            _prefix(jti),
        )
        raise InvalidTokenError("jkt_mismatch")

    user_id = stored["user_id"]
    role = stored["role"]
    pair = await issue_pair(
        redis_client, user_id, role, cnf_jkt=proof_jkt,
    )
    logger.info("refresh rotated user_id=%s role=%s", user_id, role)
    return pair


async def revoke(
    redis_client: redis.Redis,
    refresh_token: str,
    *,
    proof_jkt: str,
) -> None:
    """Delete a refresh token's jti. Idempotent.

    Args:
        redis_client: Active async Redis client.
        refresh_token: The token to revoke.
        proof_jkt: Thumbprint of the key that signed the DPoP proof.

    Raises:
        InvalidTokenError: The token is malformed, expired, of the wrong
            type, or its ``cnf.jkt`` does not match ``proof_jkt``.
    """
    claims = decode_refresh_token(refresh_token)
    jti = claims["jti"]
    token_jkt = _extract_cnf_jkt(claims)

    if token_jkt != proof_jkt:
        raise InvalidTokenError("jkt_mismatch")

    raw = await redis_client.getdel(_key(jti))
    if raw is not None:
        stored = json.loads(raw)
        if stored.get("jkt") != proof_jkt:
            logger.warning(
                "refresh revoke burned jti_prefix=%s reason=stored_jkt_mismatch",
                _prefix(jti),
            )
            raise InvalidTokenError("jkt_mismatch")

    logger.info("refresh revoked jti_prefix=%s", _prefix(jti))