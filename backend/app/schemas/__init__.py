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
from app.schemas.damage_report import (
    DamageReportCreate,
    DamageReportRead,
    ReturnDamage,
)
from app.schemas.delivery import DeliveryCreate, DeliveryRead, DeliveryStatus
from app.schemas.employee import (
    EmployeeCreate,
    EmployeeRead,
    EmployeeRole,
    EmployeeUpdate,
)
from app.schemas.game_copy import (
    GameCopyCreate,
    GameCopyRead,
    GameCopyStatus,
    GameCopyUpdate,
)
from app.schemas.order import (
    OrderCreate,
    OrderDetailRead,
    OrderItemRead,
    OrderRead,
    OrderReturnCreate,
    OrderReturnResult,
    OrderStatus,
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
    "DamageReportCreate",
    "DamageReportRead",
    "DeliveryCreate",
    "DeliveryRead",
    "DeliveryStatus",
    "EmployeeCreate",
    "EmployeeRead",
    "EmployeeRole",
    "EmployeeUpdate",
    "GameCopyCreate",
    "GameCopyRead",
    "GameCopyStatus",
    "GameCopyUpdate",
    "OrderCreate",
    "OrderDetailRead",
    "OrderItemRead",
    "OrderRead",
    "OrderReturnCreate",
    "OrderReturnResult",
    "OrderStatus",
    "PickupPointCreate",
    "PickupPointRead",
    "PickupPointUpdate",
    "ReturnDamage",
]