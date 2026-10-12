"""Shared Pydantic base classes for the schema layer."""

from pydantic import BaseModel, ConfigDict


class ORMBase(BaseModel):
    """Mixin for Read schemas.

    ``from_attributes=True`` enables ``Model.model_validate(orm_obj)`` and, in
    FastAPI, ``response_model=SomeRead`` returned straight from a SQLAlchemy
    instance.
    """

    model_config = ConfigDict(from_attributes=True)