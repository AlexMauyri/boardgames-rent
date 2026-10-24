"""Employee API contracts."""

from datetime import datetime
from typing import Literal, Protocol

from pydantic import BaseModel, EmailStr, Field, model_validator

from app.schemas.base import ORMBase

EmployeeRole = Literal["COURIER", "MANAGER", "ADMIN"]


class _RoleAndPoint(Protocol):
    """Structural type for the values ``validate_against`` reads."""

    role: str
    pickup_point_id: int | None


class EmployeeCreate(BaseModel):
    """Payload for creating an employee.

    Attributes:
        email: Login address.
        password: Plaintext password, hashed by the service layer.
        full_name: Display name.
        phone: Contact phone number.
        role: One of COURIER, MANAGER, ADMIN.
        pickup_point_id: Assigned pickup point. Required when `role` is
            MANAGER, forbidden otherwise — enforced by a model validator.
    """

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
    """Employee as returned by the API."""

    id: int
    email: EmailStr
    full_name: str
    phone: str
    role: str
    pickup_point_id: int | None
    created_at: datetime
    is_active: bool


class EmployeeUpdate(BaseModel):
    """Partial employee update; unset fields are left alone."""

    full_name: str | None = None
    phone: str | None = None
    role: EmployeeRole | None = None
    pickup_point_id: int | None = None

    def validate_against(self, current: _RoleAndPoint) -> None:
        """Validate the role/pickup-point pairing against the merged state.

        Args:
            current: The existing employee row about to be updated. Only
                `role` and `pickup_point_id` are read from it.

        Raises:
            ValueError: The merged values violate the role/point pairing.
        """
        effective_role = (
            self.role
            if "role" in self.model_fields_set
            else current.role
        )
        effective_point = (
            self.pickup_point_id
            if "pickup_point_id" in self.model_fields_set
            else current.pickup_point_id
        )

        if effective_role == "MANAGER" and effective_point is None:
            raise ValueError("MANAGER must be assigned to a pickup_point_id")
        if effective_role != "MANAGER" and effective_point is not None:
            raise ValueError(
                "pickup_point_id may only be set when role is MANAGER"
            )