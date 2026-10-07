"""Damage report API contracts."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.base import ORMBase


class DamageReportCreate(BaseModel):
    """Payload for filing a damage report.

    The reporting employee comes from the auth context, so it is not accepted
    here.

    Attributes:
        game_copy_id: The damaged box.
        order_id: The rental during which the damage was found; None for a
            routine inspection.
        description: What is damaged or missing.
        deposit_withheld: Amount kept from the client's deposit, non-negative.
    """

    game_copy_id: int
    order_id: int | None = None
    description: str = Field(min_length=1)
    deposit_withheld: Decimal = Field(default=Decimal("0"), ge=0)


class ReturnDamage(BaseModel):
    """One damaged box found while accepting a return.

    The order and the reporting manager are implied by the return itself.

    Attributes:
        game_copy_id: The damaged box; must belong to the returned order.
        description: What is damaged or missing.
        deposit_withheld: Amount kept from the client's deposit, non-negative.
    """

    game_copy_id: int
    description: str = Field(min_length=1)
    deposit_withheld: Decimal = Field(default=Decimal("0"), ge=0)


class DamageReportRead(ORMBase):
    """Damage report as returned by the API.

    Attributes:
        id: Primary key.
        game_copy_id: The damaged box.
        order_id: Related order, or None.
        reported_by: The employee who filed the report.
        description: What is damaged or missing.
        deposit_withheld: Amount kept from the deposit.
        created_at: Filing timestamp.
        resolved_at: Repair or write-off timestamp; None while open.
    """

    id: int
    game_copy_id: int
    order_id: int | None
    reported_by: int
    description: str
    deposit_withheld: Decimal
    created_at: datetime
    resolved_at: datetime | None
