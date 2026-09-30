from pydantic import BaseModel, ConfigDict


class ORMBase(BaseModel):
    """Mixin for Read schemas.

    ``from_attributes=True`` is what allows ``Model.model_validate(orm_obj)``
    and, in FastAPI, ``response_model=SomeRead`` returned straight from a
    SQLAlchemy instance. Deliberately minimal: adding fields here would leak
    into every Read schema in the project.
    """

    model_config = ConfigDict(from_attributes=True)