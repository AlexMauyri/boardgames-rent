"""Aggregating router for /api/v1."""

from fastapi import APIRouter

from app.api.v1 import auth, courier, damage, manager, orders

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(orders.router, prefix="/orders", tags=["orders"])
api_router.include_router(courier.router, prefix="/courier", tags=["courier"])
api_router.include_router(manager.router, prefix="/manager", tags=["manager"])
api_router.include_router(damage.router, prefix="/damage-reports", tags=["damage"])