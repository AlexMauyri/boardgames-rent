"""Game copy API contracts."""

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.base import ORMBase

GameCopyStatus = Literal["AVAILABLE", "WITH_CLIENT", "IN_TRANSIT", "DAMAGED"]


class GameCopyCreate(BaseModel):
    """Payload for registering a new physical box.

    A new box always starts AVAILABLE at a pickup point.

    Attributes:
        game_id: Catalog entry the box is a copy of.
        current_point_id: Pickup point where the box is placed.
        inventory_number: Unique barcode label.
    """

    game_id: int
    current_point_id: int
    inventory_number: str = Field(min_length=1, max_length=50)


class GameCopyRead(ORMBase):
    """Game copy as returned by the API.

    Attributes:
        id: Primary key.
        game_id: Catalog entry the box is a copy of.
        current_point_id: Holding pickup point; None with a client or in transit.
        inventory_number: Unique barcode label.
        status: One of AVAILABLE, WITH_CLIENT, IN_TRANSIT, DAMAGED.
    """

    id: int
    game_id: int
    current_point_id: int | None
    inventory_number: str
    status: GameCopyStatus


class GameCopyUpdate(BaseModel):
    """Partial game copy update; unset fields are left alone.

    Status and location are not editable here: they change only through the
    order and delivery flows in the service layer.
    """

    inventory_number: str | None = Field(default=None, min_length=1, max_length=50)
