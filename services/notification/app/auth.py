"""JWT check for WebSocket connections.

Access tokens are issued by the API service and signed with the shared
``JWT_SECRET``; this service only verifies them and never issues tokens.
"""

from dataclasses import dataclass

import jwt

from app.config import settings


class AuthError(Exception):
    """The token cannot be trusted; the reason is for logs, not for clients."""


@dataclass(frozen=True)
class Principal:
    """Who is on the other end of a connection.

    Attributes:
        id: Client or employee primary key.
        role: ``CLIENT``, ``COURIER``, ``MANAGER`` or ``ADMIN``.
    """

    id: int
    role: str


def authenticate(token: str) -> Principal:
    """Verify an access token and return its subject.

    Args:
        token: Compact JWT as issued by the API service.

    Returns:
        The token's subject and role.

    Raises:
        AuthError: Bad signature, expired, not an access token, or the
            ``sub``/``role`` claims are missing or malformed.
    """
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "sub", "role", "type"]},
        )
    except jwt.InvalidTokenError as exc:
        raise AuthError(f"invalid token: {exc}") from exc

    if claims["type"] != "access":
        raise AuthError("not an access token")
    role = claims["role"]
    if not isinstance(role, str) or not role:
        raise AuthError("malformed role")
    try:
        user_id = int(claims["sub"])
    except (TypeError, ValueError) as exc:
        raise AuthError("malformed subject") from exc
    return Principal(id=user_id, role=role)
