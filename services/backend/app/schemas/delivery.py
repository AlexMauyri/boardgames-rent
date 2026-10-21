"""Delivery API contracts."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, model_validator

from app.schemas.base import ORMBase

DeliveryStatus = Literal["CREATED", "ACCEPTED", "IN_TRANSIT", "DELIVERED"]


class DeliveryCreate(BaseModel):
    """Payload for creating a transfer task; issued by the order flow.

    Attributes:
        order_id: The order being served.
        from_point_id: Pickup point the box is taken from.
        to_point_id: Pickup point the box is brought to; must differ from
            `from_point_id`.
    """

    order_id: int
    from_point_id: int
    to_point_id: int

    @model_validator(mode="after")
    def _validate_points(self) -> "DeliveryCreate":
        if self.from_point_id == self.to_point_id:
            raise ValueError("from_point_id and to_point_id must differ")
        return self


class DeliveryRead(ORMBase):
    """Delivery as returned by the API.

    Attributes:
        id: Primary key.
        order_id: The served order.
        courier_id: Assigned courier; None until accepted.
        from_point_id: Departure point.
        to_point_id: Destination point.
        status: One of CREATED, ACCEPTED, IN_TRANSIT, DELIVERED.
        created_at: Task creation timestamp.
        delivered_at: Completion timestamp; None while unfinished.
    """

    id: int
    order_id: int
    courier_id: int | None
    from_point_id: int
    to_point_id: int
    status: DeliveryStatus
    created_at: datetime
    delivered_at: datetime | None
