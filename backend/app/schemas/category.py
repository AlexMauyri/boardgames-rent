"""Category API contracts."""

from pydantic import BaseModel

from app.schemas.base import ORMBase


class CategoryCreate(BaseModel):
    """Payload for creating a category.

    Attributes:
        name: Unique category name.
    """

    name: str


class CategoryRead(ORMBase):
    """Category as returned by the API.

    Attributes:
        id: Primary key.
        name: Category name.
    """

    id: int
    name: str


class CategoryUpdate(BaseModel):
    """Partial category update; unset fields are left alone.

    Attributes:
        name: New category name, if renaming.
    """

    name: str | None = None