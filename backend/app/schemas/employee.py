from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, model_validator

from app.schemas.base import ORMBase

EmployeeRole = Literal["COURIER", "MANAGER", "ADMIN"]


class EmployeeCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    full_name: str
    phone: str
    role: EmployeeRole
    pickup_point_id: int | None = None

    @model_validator(mode="after")
    def _validate_role_and_point(self) -> "EmployeeCreate":
        if self.role == "MANAGER" and self.pickup_point_id is None:
            raise ValueError("MANAGER must be assigned to a pickup_point_id")
        if self.role != "MANAGER" and self.pickup_point_id is not None:
            raise ValueError(
                "pickup_point_id may only be set when role is MANAGER"
            )
        return self


class EmployeeRead(ORMBase):
    id: int
    email: EmailStr
    full_name: str
    phone: str
    role: str
    pickup_point_id: int | None
    created_at: datetime


class EmployeeUpdate(BaseModel):
    full_name: str | None = None
    phone: str | None = None
    role: EmployeeRole | None = None
    pickup_point_id: int | None = None

    @model_validator(mode="after")
    def _validate_role_and_point(self) -> "EmployeeUpdate":
        if self.role is None or self.pickup_point_id is None:
            return self
        if self.role != "MANAGER":
            raise ValueError(
                "pickup_point_id may only be set when role is MANAGER"
            )
        return self