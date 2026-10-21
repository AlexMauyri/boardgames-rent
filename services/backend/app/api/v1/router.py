"""Aggregating router for /api/v1."""

from fastapi import APIRouter

from app.api.v1 import auth, catalog, courier, damage, manager, orders
from app.api.v1.admin.router import admin_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(catalog.router, prefix="/catalog", tags=["catalog"])
api_router.include_router(orders.router, prefix="/orders", tags=["orders"])
api_router.include_router(courier.router, prefix="/courier", tags=["courier"])
api_router.include_router(manager.router, prefix="/manager", tags=["manager"])
api_router.include_router(damage.router, prefix="/damage-reports", tags=["damage"])
api_router.include_router(admin_router, prefix="/admin", tags=["admin"])
