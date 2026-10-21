"""Pickup point manager router: view the point, issue, accept returns.

A manager works only on the point they are assigned to. Every endpoint is
gated by ``require_role("MANAGER")``; the manager's id and point come from
the token, never from the request body.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session, require_role
from app.db.models import Employee
from app.schemas import (
    DamageReportCreate,
    DamageReportRead,
    GameCopyRead,
    OrderDetailRead,
    OrderRead,
    OrderReturnCreate,
    OrderReturnResult,
)
from app.schemas.order import OrderStatus
from app.services import damage as damage_service
from app.services import manager as manager_service

router = APIRouter()

_Manager = Annotated[Employee, Depends(require_role("MANAGER"))]


@router.get("/orders", response_model=list[OrderRead])
async def list_point_orders(
    manager: _Manager,
    session: Annotated[AsyncSession, Depends(get_session)],
    status: OrderStatus | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1),
) -> list[OrderRead]:
    """List orders collected at the manager's point, newest first."""
    return await manager_service.list_point_orders(
        session, manager.id, status=status, skip=skip, limit=limit,
    )


@router.get("/orders/{order_id}", response_model=OrderDetailRead)
async def find_point_order(
    order_id: int,
    manager: _Manager,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> OrderDetailRead:
    """Look up an order by number among the manager's point's orders."""
    return await manager_service.find_point_order(session, manager.id, order_id)


@router.get("/inventory", response_model=list[GameCopyRead])
async def list_point_inventory(
    manager: _Manager,
    session: Annotated[AsyncSession, Depends(get_session)],
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1),
) -> list[GameCopyRead]:
    """List the boxes physically on the manager's point's shelves."""
    return await manager_service.list_point_inventory(
        session, manager.id, skip=skip, limit=limit,
    )


@router.post("/orders/{order_id}/issue", response_model=OrderRead)
async def issue_order(
    order_id: int,
    manager: _Manager,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> OrderRead:
    """Hand the boxes to the client; the order becomes ACTIVE."""
    return await manager_service.issue_order(session, order_id, manager.id)


@router.post("/orders/{order_id}/return", response_model=OrderReturnResult)
async def accept_return(
    order_id: int,
    payload: OrderReturnCreate,
    manager: _Manager,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> OrderReturnResult:
    """Take the boxes back; the order becomes COMPLETED."""
    return await manager_service.accept_return(
        session, order_id, manager.id, payload,
    )


@router.post("/damage-reports", response_model=DamageReportRead)
async def report_damage(
    payload: DamageReportCreate,
    manager: _Manager,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DamageReportRead:
    """File a routine inspection report on a shelf box."""
    return await damage_service.report_damage(session, manager.id, payload)