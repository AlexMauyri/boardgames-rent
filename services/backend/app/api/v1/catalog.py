"""Public catalog router: categories, pickup points, games, stock search.

No authentication. Reference data is served through the Redis cache
(`catalog_cache`); stock search always hits the database, because free box
counts change with every order.
"""

from typing import Annotated

import redis.asyncio as redis
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_redis,
    get_recommendation_client,
    get_session,
)
from app.crud import board_game, game_copy
from app.integrations.grpc.recommendation_client import RecommendationClient
from app.schemas import (
    BoardGameRead,
    CategoryRead,
    GameSearchItem,
    PickupPointRead,
    SimilarGameItem,
)
from app.services import catalog as catalog_service
from app.services import catalog_cache
from app.services.exceptions import NotFoundError

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


@router.get(
    "/games/{game_id}/similar",
    response_model=list[SimilarGameItem],
)
async def get_similar_games(
    game_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    recommendation_client: Annotated[
        RecommendationClient, Depends(get_recommendation_client)
    ],
    limit: Annotated[int, Query(ge=1)] = 10,
) -> list[SimilarGameItem]:
    """Return games similar to ``game_id``, filtered by availability.

    Raises:
        NotFoundError: No board game with that id.
    """
    target = await board_game.get(session, game_id)
    if target is None:
        raise NotFoundError("BoardGame", game_id)

    recs = await recommendation_client.get_similar_games(
        target_game_id=game_id,
        exclude_game_ids=[game_id],
        limit=limit * 3,
    )
    if not recs:
        return []

    candidate_ids = [r.game_id for r in recs]
    free_copies = await game_copy.count_free(session, candidate_ids)
    available_ids = {g for (g, _) in free_copies.keys()}

    filtered = [r for r in recs if r.game_id in available_ids][:limit]
    if not filtered:
        return []

    games = await board_game.get_many(session, [r.game_id for r in filtered])
    games_by_id = {g.id: g for g in games}

    return [
        SimilarGameItem(
            game=BoardGameRead.model_validate(games_by_id[r.game_id]),
            reason=r.reason,
        )
        for r in filtered
        if r.game_id in games_by_id
    ]