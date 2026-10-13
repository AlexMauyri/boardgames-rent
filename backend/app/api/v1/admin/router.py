"""Aggregating router for /api/v1/admin.

The ADMIN role is enforced once here, for every endpoint below; individual
routers do not repeat it.
"""

from fastapi import APIRouter, Depends

from app.api.deps import require_role
from app.api.v1.admin import (
    categories,
    clients,
    copies,
    employees,
    games,
    pickup_points,
)

admin_router = APIRouter(dependencies=[Depends(require_role("ADMIN"))])
admin_router.include_router(categories.router, prefix="/categories")
admin_router.include_router(clients.router, prefix="/clients")
admin_router.include_router(employees.router, prefix="/employees")
admin_router.include_router(games.router, prefix="/games")
admin_router.include_router(pickup_points.router, prefix="/pickup-points")
admin_router.include_router(copies.router, prefix="/copies")
