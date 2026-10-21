"""Courier router: open tasks, own tasks, and status transitions."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session, require_role
from app.db.models import Employee
from app.schemas import DeliveryRead
from app.services import deliveries as deliveries_service

router = APIRouter()

_Courier = Annotated[Employee, Depends(require_role("COURIER"))]


@router.get("/deliveries/open", response_model=list[DeliveryRead])
async def list_open_deliveries(
    courier: _Courier,
    session: Annotated[AsyncSession, Depends(get_session)],
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1),
) -> list[DeliveryRead]:
    """List delivery tasks no courier has accepted yet."""
    return await deliveries_service.list_open_deliveries(
        session, skip=skip, limit=limit,
    )


@router.get("/deliveries", response_model=list[DeliveryRead])
async def list_own_deliveries(
    courier: _Courier,
    session: Annotated[AsyncSession, Depends(get_session)],
    active_only: bool = Query(True),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1),
) -> list[DeliveryRead]:
    """List the calling courier's tasks. `active_only` defaults to True."""
    return await deliveries_service.list_courier_deliveries(
        session, courier.id, active_only=active_only, skip=skip, limit=limit,
    )


@router.post("/deliveries/{delivery_id}/accept", response_model=DeliveryRead)
async def accept_delivery(
    delivery_id: int,
    courier: _Courier,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DeliveryRead:
    """Take an open task. The calling courier becomes its assignee."""
    return await deliveries_service.accept_delivery(
        session, delivery_id, courier.id,
    )


@router.post("/deliveries/{delivery_id}/start", response_model=DeliveryRead)
async def start_delivery(
    delivery_id: int,
    courier: _Courier,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DeliveryRead:
    """Mark the boxes as picked up and on the road."""
    return await deliveries_service.start_delivery(
        session, delivery_id, courier.id,
    )


@router.post("/deliveries/{delivery_id}/complete", response_model=DeliveryRead)
async def complete_delivery(
    delivery_id: int,
    courier: _Courier,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DeliveryRead:
    """Hand the boxes over at the destination."""
    return await deliveries_service.complete_delivery(
        session, delivery_id, courier.id,
    )