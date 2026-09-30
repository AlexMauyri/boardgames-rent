"""Pydantic v2 schema layer."""

from app.schemas.base import ORMBase
from app.schemas.board_game import (
    BoardGameCreate,
    BoardGameRead,
    BoardGameUpdate,
    CoverUploadResponse,
)
from app.schemas.category import CategoryCreate, CategoryRead, CategoryUpdate
from app.schemas.client import ClientCreate, ClientRead, ClientUpdate
from app.schemas.employee import (
    EmployeeCreate,
    EmployeeRead,
    EmployeeRole,
    EmployeeUpdate,
)
from app.schemas.pickup_point import (
    PickupPointCreate,
    PickupPointRead,
    PickupPointUpdate,
)

__all__ = [
    "ORMBase",
    "BoardGameCreate",
    "BoardGameRead",
    "BoardGameUpdate",
    "CoverUploadResponse",
    "CategoryCreate",
    "CategoryRead",
    "CategoryUpdate",
    "ClientCreate",
    "ClientRead",
    "ClientUpdate",
    "EmployeeCreate",
    "EmployeeRead",
    "EmployeeRole",
    "EmployeeUpdate",
    "PickupPointCreate",
    "PickupPointRead",
    "PickupPointUpdate",
]