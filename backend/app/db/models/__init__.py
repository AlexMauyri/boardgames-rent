"""Model registry."""

from app.db.models.board_game import BoardGame
from app.db.models.category import Category
from app.db.models.client import Client
from app.db.models.damage_report import DamageReport
from app.db.models.delivery import Delivery
from app.db.models.employee import Employee
from app.db.models.game_category import game_categories
from app.db.models.game_copy import GameCopy
from app.db.models.order import Order
from app.db.models.order_item import OrderItem
from app.db.models.pickup_point import PickupPoint

__all__ = [
    "BoardGame",
    "Category",
    "Client",
    "DamageReport",
    "Delivery",
    "Employee",
    "GameCopy",
    "Order",
    "OrderItem",
    "PickupPoint",
    "game_categories",
]
