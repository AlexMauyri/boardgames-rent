from pydantic import BaseModel

from app.schemas.base import ORMBase


class PickupPointCreate(BaseModel):
    name: str
    address: str
    phone: str
    is_active: bool = True


class PickupPointRead(ORMBase):
    id: int
    name: str
    address: str
    phone: str
    is_active: bool


class PickupPointUpdate(BaseModel):
    name: str | None = None
    address: str | None = None
    phone: str | None = None
    is_active: bool | None = None