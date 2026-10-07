"""Service layer."""

from app.services.admin_categories import (
    create_category,
    delete_category,
    update_category,
)
from app.services.admin_clients import activate_client, deactivate_client
from app.services.admin_employees import (
    assign_manager_to_point,
    change_employee_role,
    create_employee,
    list_employees,
    update_employee,
)
from app.services.admin_games import (
    add_new_game_to_catalog,
    set_game_categories,
    update_game,
)
from app.services.admin_pickup_points import (
    activate_pickup_point,
    create_pickup_point,
    deactivate_pickup_point,
    list_pickup_points_admin,
    update_pickup_point,
)
from app.services.auth import (
    authenticate_client,
    authenticate_employee,
    register_client,
)
from app.services.catalog import (
    get_game_detail,
    list_categories,
    list_pickup_points_public,
)
from app.services.deliveries import (
    accept_delivery,
    complete_delivery,
    list_courier_deliveries,
    list_open_deliveries,
    start_delivery,
)
from app.services.exceptions import (
    ConflictError,
    ForbiddenError,
    InvalidTransitionError,
    NotAvailableError,
    NotFoundError,
)
from app.services.orders import (
    cancel_order,
    create_order,
    get_order,
    list_client_orders,
)

__all__ = [
    "ConflictError",
    "ForbiddenError",
    "InvalidTransitionError",
    "NotAvailableError",
    "NotFoundError",
    "accept_delivery",
    "activate_client",
    "activate_pickup_point",
    "add_new_game_to_catalog",
    "assign_manager_to_point",
    "authenticate_client",
    "authenticate_employee",
    "cancel_order",
    "change_employee_role",
    "complete_delivery",
    "create_category",
    "create_employee",
    "create_order",
    "create_pickup_point",
    "deactivate_client",
    "deactivate_pickup_point",
    "delete_category",
    "get_game_detail",
    "get_order",
    "list_categories",
    "list_client_orders",
    "list_courier_deliveries",
    "list_employees",
    "list_open_deliveries",
    "list_pickup_points_admin",
    "list_pickup_points_public",
    "register_client",
    "start_delivery",
    "set_game_categories",
    "update_category",
    "update_employee",
    "update_game",
    "update_pickup_point",
]