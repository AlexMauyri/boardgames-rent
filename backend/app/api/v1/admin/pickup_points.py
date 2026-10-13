"""Admin: pickup points. Every change drops the cached public point list."""

from typing import Annotated

import redis.asyncio as redis
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_redis, get_session
from app.schemas import PickupPointCreate, PickupPointRead, PickupPointUpdate
from app.services import admin_pickup_points, catalog_cache

router = APIRouter()


@router.get("", response_model=list[PickupPointRead])
async def list_pickup_points(
    session: Annotated[AsyncSession, Depends(get_session)],
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1),
) -> list[PickupPointRead]:
    """List every pickup point, deactivated ones included. Not cached."""
    return await admin_pickup_points.list_pickup_points_admin(
        session, skip=skip, limit=limit,
    )


@router.post(
    "",
    response_model=PickupPointRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_pickup_point(
    payload: PickupPointCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    redis_client: Annotated[redis.Redis, Depends(get_redis)],
) -> PickupPointRead:
    """Open a new pickup point. 409 if the name is taken."""
    result = await admin_pickup_points.create_pickup_point(session, payload)
    await catalog_cache.invalidate_catalog(redis_client, points=True)
    return result


@router.put("/{point_id}", response_model=PickupPointRead)
async def update_pickup_point(
    point_id: int,
    payload: PickupPointUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    redis_client: Annotated[redis.Redis, Depends(get_redis)],
) -> PickupPointRead:
    """Edit a pickup point. 409 if the new name is taken."""
    result = await admin_pickup_points.update_pickup_point(
        session, point_id, payload,
    )
    await catalog_cache.invalidate_catalog(redis_client, points=True)
    return result


@router.post("/{point_id}/activate", response_model=PickupPointRead)
async def activate_pickup_point(
    point_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    redis_client: Annotated[redis.Redis, Depends(get_redis)],
) -> PickupPointRead:
    """Switch a pickup point back on."""
    result = await admin_pickup_points.activate_pickup_point(session, point_id)
    await catalog_cache.invalidate_catalog(redis_client, points=True)
    return result


@router.post("/{point_id}/deactivate", response_model=PickupPointRead)
async def deactivate_pickup_point(
    point_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    redis_client: Annotated[redis.Redis, Depends(get_redis)],
) -> PickupPointRead:
    """Switch a pickup point off; it disappears from the public list."""
    result = await admin_pickup_points.deactivate_pickup_point(
        session, point_id,
    )
    await catalog_cache.invalidate_catalog(redis_client, points=True)
    return result
