"""Authentication API contracts."""

from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    """Payload for client or employee login.

    Attributes:
        email: Login address.
        password: Plaintext password as submitted.
    """

    email: EmailStr
    password: str = Field(min_length=1)


class TokenPair(BaseModel):
    """A freshly issued access + refresh token pair.

    Attributes:
        access_token: Short-lived token for the Authorization header.
        refresh_token: Long-lived token exchanged at /auth/refresh.
        token_type: Always "bearer"; kept explicit for OAuth2 clients.
    """

    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"


class RefreshRequest(BaseModel):
    """Payload for exchanging a refresh token for a new pair.

    Attributes:
        refresh_token: The refresh token to rotate. Its jti must still be
            registered in Redis; an unknown or revoked jti is rejected.
    """

    refresh_token: str = Field(min_length=1)