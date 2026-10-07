"""Order API contracts."""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.base import ORMBase
from app.schemas.damage_report import DamageReportRead, ReturnDamage

OrderStatus = Literal[
    "CREATED",
    "NEEDS_TRANSFER",
    "IN_TRANSIT",
    "READY_FOR_PICKUP",
    "ACTIVE",
    "COMPLETED",
    "CANCELLED",
]


class OrderCreate(BaseModel):
    """Payload for placing a rental order.

    The client picks games, not boxes; the service layer chooses concrete
    boxes. The client id comes from the auth context, and prices are computed,
    so neither is accepted here.

    Attributes:
        pickup_point_id: Pickup point where the client collects the games.
        start_date: First day of the rental.
        end_date: Last day of the rental, not before `start_date`.
        game_ids: Catalog games to rent, at least one.
    """

    pickup_point_id: int
    start_date: date
    end_date: date
    game_ids: list[int] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_dates(self) -> "OrderCreate":
        if self.end_date < self.start_date:
            raise ValueError("end_date must be >= start_date")
        return self


class OrderItemRead(ORMBase):
    """Order line as returned by the API.

    Attributes:
        game_copy_id: The rented box.
        price_at_rental: Tariff frozen at booking time.
    """

    game_copy_id: int
    price_at_rental: Decimal


class OrderRead(ORMBase):
    """Order as returned by the API, without its lines.

    Attributes:
        id: Booking number.
        client_id: The ordering client.
        pickup_point_id: Collection point.
        start_date: First day of the rental.
        end_date: Last day of the rental.
        total_price: Total rental cost.
        deposit_paid: Deposit taken from the client.
        status: Current order status.
        created_at: Placement timestamp.
    """

    id: int
    client_id: int
    pickup_point_id: int
    start_date: date
    end_date: date
    total_price: Decimal
    deposit_paid: Decimal
    status: OrderStatus
    created_at: datetime


class OrderDetailRead(OrderRead):
    """Order with its lines; the order's `items` must be eagerly loaded."""

    items: list[OrderItemRead]


class OrderReturnCreate(BaseModel):
    """Payload for accepting a returned order at a pickup point.

    Attributes:
        damages: Damaged boxes found on inspection, at most one entry per
            box; empty when everything is intact.
    """

    damages: list[ReturnDamage] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_unique_boxes(self) -> "OrderReturnCreate":
        ids = [d.game_copy_id for d in self.damages]
        if len(ids) != len(set(ids)):
            raise ValueError("each box may be reported at most once")
        return self


class OrderReturnResult(BaseModel):
    """Outcome of accepting a return.

    Attributes:
        order: The completed order.
        damage_reports: Reports filed during this return.
        deposit_refund: Deposit paid minus everything withheld.
    """

    order: OrderRead
    damage_reports: list[DamageReportRead]
    deposit_refund: Decimal
