from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.schemas.base import ORMBase


class ClientCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    full_name: str
    phone: str


class ClientRead(ORMBase):
    id: int
    email: EmailStr
    full_name: str
    phone: str
    created_at: datetime


class ClientUpdate(BaseModel):
    full_name: str | None = None
    phone: str | None = None