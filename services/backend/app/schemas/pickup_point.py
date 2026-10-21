"""Pickup point API contracts."""

from pydantic import BaseModel

from app.schemas.base import ORMBase


class PickupPointCreate(BaseModel):
    """Payload for creating a pickup point.
    
    Attributes:
        name: Unique point name.
        address: Physical address.
        phone: Contact phone number.
    """

    name: str
    address: str
    phone: str


class PickupPointRead(ORMBase):
    """Pickup point as returned by the API.

    Attributes:
        id: Primary key.
        name: Display name.
        address: Physical address.
        phone: Contact phone number.
        is_active: False hides the point from the public list.
    """

    id: int
    name: str
    address: str
    phone: str
    is_active: bool


class PickupPointUpdate(BaseModel):
    """Partial pickup point update; unset fields are left alone.

    Attributes:
        name: New point name, if renaming.
        address: New physical address.
        phone: New contact phone number.
    """

    name: str | None = None
    address: str | None = None
    phone: str | None = None