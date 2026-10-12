"""Aggregating router for /api/v1."""

from fastapi import APIRouter

from app.api.v1 import auth, courier, orders

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(orders.router, prefix="/orders", tags=["orders"])
api_router.include_router(courier.router, prefix="/courier", tags=["courier"])