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
from app.services.exceptions import ConflictError, NotFoundError

__all__ = [
    "ConflictError",
    "NotFoundError",
    "activate_client",
    "activate_pickup_point",
    "add_new_game_to_catalog",
    "assign_manager_to_point",
    "authenticate_client",
    "authenticate_employee",
    "change_employee_role",
    "create_category",
    "create_employee",
    "create_pickup_point",
    "deactivate_client",
    "deactivate_pickup_point",
    "delete_category",
    "get_game_detail",
    "list_categories",
    "list_employees",
    "list_pickup_points_admin",
    "list_pickup_points_public",
    "register_client",
    "set_game_categories",
    "update_category",
    "update_employee",
    "update_game",
    "update_pickup_point",
]