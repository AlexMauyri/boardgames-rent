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
        access_token: Short-lived Bearer token for the Authorization
            header on API endpoints.
        refresh_token: Long-lived DPoP-bound token exchanged at
            ``/auth/refresh``; requires a matching DPoP proof.
        token_type: Always ``"DPoP"`` for the refresh flow. API
            requests use ``Authorization: Bearer <access_token>``.
    """

    access_token: str
    refresh_token: str
    token_type: Literal["DPoP"] = "DPoP"


class RefreshRequest(BaseModel):
    """Payload for exchanging a refresh token for a new pair.

    Attributes:
        refresh_token: The refresh token to rotate. Its jti must still be
            registered in Redis; an unknown or revoked jti is rejected.
    """

    refresh_token: str = Field(min_length=1)