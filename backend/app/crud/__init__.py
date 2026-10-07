"""CRUD layer."""

from app.crud.base import CRUDBase
from app.crud.board_game import (
    CRUDBoardGame,
    board_game,
    set_categories,
)
from app.crud.category import CRUDCategory, category
from app.crud.client import CRUDClient, client
from app.crud.damage_report import CRUDDamageReport, damage_report
from app.crud.delivery import CRUDDelivery, delivery
from app.crud.employee import CRUDEmployee, employee
from app.crud.game_copy import CRUDGameCopy, game_copy
from app.crud.order import CRUDOrder, order
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
    "CRUDDamageReport",
    "damage_report",
    "CRUDDelivery",
    "delivery",
    "CRUDEmployee",
    "employee",
    "CRUDGameCopy",
    "game_copy",
    "CRUDOrder",
    "order",
    "CRUDPickupPoint",
    "pickup_point",
]