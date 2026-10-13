"""Public catalog router: categories, pickup points, games, stock search.

No authentication. Reference data is served through the Redis cache
(`catalog_cache`); stock search always hits the database, because free box
counts change with every order.
"""

from typing import Annotated

import redis.asyncio as redis
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_redis, get_session
from app.schemas import (
    BoardGameRead,
    CategoryRead,
    GameSearchItem,
    PickupPointRead,
)
from app.services import catalog as catalog_service
from app.services import catalog_cache

router = APIRouter()


@router.get("/categories", response_model=list[CategoryRead])
async def list_categories(
    session: Annotated[AsyncSession, Depends(get_session)],
    redis_client: Annotated[redis.Redis, Depends(get_redis)],
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1),
) -> list[CategoryRead]:
    """List all categories."""
    return await catalog_cache.list_categories(
        redis_client, session, skip=skip, limit=limit,
    )


@router.get("/pickup-points", response_model=list[PickupPointRead])
async def list_pickup_points(
    session: Annotated[AsyncSession, Depends(get_session)],
    redis_client: Annotated[redis.Redis, Depends(get_redis)],
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1),
) -> list[PickupPointRead]:
    """List active pickup points."""
    return await catalog_cache.list_pickup_points_public(
        redis_client, session, skip=skip, limit=limit,
    )


@router.get("/games", response_model=list[BoardGameRead])
async def list_games(
    session: Annotated[AsyncSession, Depends(get_session)],
    redis_client: Annotated[redis.Redis, Depends(get_redis)],
    players: int | None = Query(None, ge=1),
    playtime_max: int | None = Query(None, ge=1),
    category_id: int | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1),
) -> list[BoardGameRead]:
    """Browse the catalog, optionally filtered."""
    return await catalog_cache.list_games(
        redis_client,
        session,
        players=players,
        playtime_max=playtime_max,
        category_id=category_id,
        skip=skip,
        limit=limit,
    )


@router.get("/games/{game_id}", response_model=BoardGameRead)
async def get_game(
    game_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    redis_client: Annotated[redis.Redis, Depends(get_redis)],
) -> BoardGameRead:
    """Fetch a single game card."""
    return await catalog_cache.get_game_detail(redis_client, session, game_id)


@router.get("/search", response_model=list[GameSearchItem])
async def search_available_games(
    session: Annotated[AsyncSession, Depends(get_session)],
    pickup_point_id: int = Query(...),
    players: int | None = Query(None, ge=1),
    playtime_max: int | None = Query(None, ge=1),
    category_id: int | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1),
) -> list[GameSearchItem]:
    """Find games with free boxes that can reach the chosen point.

    Games collectable at once come first; the rest need a delivery.
    """
    return await catalog_service.search_available_games(
        session,
        pickup_point_id,
        players=players,
        playtime_max=playtime_max,
        category_id=category_id,
        skip=skip,
        limit=limit,
    )
