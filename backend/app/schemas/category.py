from pydantic import BaseModel

from app.schemas.base import ORMBase


class CategoryCreate(BaseModel):
    name: str


class CategoryRead(ORMBase):
    id: int
    name: str


class CategoryUpdate(BaseModel):
    name: str | None = None