"""Model registry."""

from app.db.models.board_game import BoardGame
from app.db.models.category import Category
from app.db.models.client import Client
from app.db.models.employee import Employee
from app.db.models.game_category import game_categories
from app.db.models.pickup_point import PickupPoint

__all__ = [
    "BoardGame",
    "Category",
    "Client",
    "Employee",
    "PickupPoint",
    "game_categories",
]