"""CRUD layer."""

from app.crud.base import CRUDBase
from app.crud.board_game import (
    CRUDBoardGame,
    board_game,
    set_categories,
)
from app.crud.category import CRUDCategory, category
from app.crud.client import CRUDClient, client
from app.crud.employee import CRUDEmployee, employee
from app.crud.pickup_point import CRUDPickupPoint, pickup_point

__all__ = [
    "CRUDBase",
    "CRUDBoardGame",
    "board_game",
    "set_categories",
    "CRUDCategory",
    "category",
    "CRUDClient",
    "client",
    "CRUDEmployee",
    "employee",
    "CRUDPickupPoint",
    "pickup_point",
]