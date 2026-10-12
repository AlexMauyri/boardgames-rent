"""JWT helpers for access and refresh tokens.

Access tokens are short-lived and stateless. Refresh tokens carry a
unique ``jti`` claim; the caller is expected to register that ``jti``
in Redis (see ``app.services.tokens``) and to verify its presence on
refresh. This module knows nothing about storage.
"""

from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import uuid4

import jwt

from app.config import settings

_TOKEN_TYPE_ACCESS = "access"
_TOKEN_TYPE_REFRESH = "refresh"

_ALGORITHM = settings.jwt_algorithm


class InvalidTokenError(Exception):
    """Raised when a token cannot be trusted.

    Covers: malformed input, wrong signature, expired token, wrong token
    type, missing required claims. The reason is carried in ``reason`` for
    logging; the HTTP layer must not expose it to the caller.
    """

    def __init__(self, reason: str) -> None:
        """Initialise the error with a short machine-readable reason.

        Args:
            reason: Short description, e.g. "expired" or "wrong type".
        """
        self.reason = reason
        super().__init__(reason)


def _now() -> datetime:
    """Return the current time in UTC, timezone-aware."""
    return datetime.now(UTC)


def _encode(payload: dict[str, Any]) -> str:
    """Sign a payload with the configured secret and algorithm.

    Args:
        payload: Claims to encode.

    Returns:
        The compact JWT string.
    """
    return jwt.encode(payload, settings.jwt_secret, algorithm=_ALGORITHM)


def _decode(token: str) -> dict[str, Any]:
    """Verify a token's signature and expiry, and return its claims.

    Args:
        token: The compact JWT string.

    Returns:
        The decoded claims.

    Raises:
        InvalidTokenError: The token is malformed, has a bad signature, or
            has expired. The reason is stored on the exception.
    """
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[_ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise InvalidTokenError("expired") from exc
    except jwt.InvalidTokenError as exc:
        raise InvalidTokenError("invalid") from exc


def _require_type(claims: dict[str, Any], expected: str) -> None:
    """Ensure the ``type`` claim matches what the caller expects.

    Args:
        claims: Decoded token claims.
        expected: The token type this endpoint accepts.

    Raises:
        InvalidTokenError: The claim is missing or differs from `expected`.
    """
    actual = claims.get("type")
    if actual != expected:
        raise InvalidTokenError(
            f"wrong token type: expected {expected!r}, got {actual!r}"
        )


def create_access_token(user_id: int, role: str) -> str:
    """Issue a short-lived access token.

    Args:
        user_id: Subject id — a client or employee primary key.
        role: "CLIENT" or an employee role.

    Returns:
        The signed compact JWT.
    """
    now = _now()
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "role": role,
        "type": _TOKEN_TYPE_ACCESS,
        "iat": now,
        "exp": now + timedelta(seconds=settings.access_token_ttl),
    }
    return _encode(payload)


def create_refresh_token(user_id: int, role: str) -> tuple[str, str]:
    """Issue a long-lived refresh token together with its unique id.

    The caller must persist ``jti`` (typically in Redis) to make the
    token revocable. Without that, the token is valid until it expires.

    Args:
        user_id: Subject id — a client or employee primary key.
        role: "CLIENT" or an employee role.

    Returns:
        A tuple ``(token, jti)``. ``jti`` is a random hex string.
    """
    now = _now()
    jti = uuid4().hex
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "role": role,
        "type": _TOKEN_TYPE_REFRESH,
        "jti": jti,
        "iat": now,
        "exp": now + timedelta(seconds=settings.refresh_token_ttl),
    }
    return _encode(payload), jti


def decode_access_token(token: str) -> dict[str, Any]:
    """Verify an access token and return its claims.

    Args:
        token: The compact JWT string.

    Returns:
        The decoded claims. ``sub`` is a string, callers should cast to int.

    Raises:
        InvalidTokenError: The token is invalid, expired, or not an access
            token.
    """
    claims = _decode(token)
    _require_type(claims, _TOKEN_TYPE_ACCESS)
    return claims


def decode_refresh_token(token: str) -> dict[str, Any]:
    """Verify a refresh token and return its claims.

    Args:
        token: The compact JWT string.

    Returns:
        The decoded claims. Contains ``jti``.

    Raises:
        InvalidTokenError: The token is invalid, expired, not a refresh
            token, or lacks a ``jti``.
    """
    claims = _decode(token)
    _require_type(claims, _TOKEN_TYPE_REFRESH)
    if not claims.get("jti"):
        raise InvalidTokenError("missing jti")
    return claims