"""Client API contracts."""

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.schemas.base import ORMBase


class ClientCreate(BaseModel):
    """Payload for client self-registration.

    Attributes:
        email: Login address.
        password: Plaintext password, hashed by the service layer. Argon2 has
            no input length limit, so no upper bound is applied here.
        full_name: Display name.
        phone: Contact phone number.
    """

    email: EmailStr
    password: str = Field(min_length=6)
    full_name: str
    phone: str


class ClientRead(ORMBase):
    """Client as returned by the API."""

    id: int
    email: EmailStr
    full_name: str
    phone: str
    created_at: datetime
    is_active: bool


class ClientUpdate(BaseModel):
    """Partial client profile update; unset fields are left alone."""

    full_name: str | None = None
    phone: str | None = None