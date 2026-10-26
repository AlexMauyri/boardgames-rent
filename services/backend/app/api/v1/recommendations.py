"""Personal recommendations for the authenticated client."""

from typing import Annotated

import redis.asyncio as redis
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_current_client,
    get_recommendation_client,
    get_redis,
    get_session,
)
from app.crud import game_copy
from app.crud import order as order_crud
from app.db.models import Client
from app.integrations.grpc.recommendation_client import RecommendationClient
from app.schemas import SimilarGameItem
from app.services import catalog_cache

router = APIRouter()


@router.get("/personal", response_model=list[SimilarGameItem])
async def get_personal_recommendations(
    client: Annotated[Client, Depends(get_current_client)],
    session: Annotated[AsyncSession, Depends(get_session)],
    recommendation_client: Annotated[
        RecommendationClient, Depends(get_recommendation_client)
    ],
    redis_client: Annotated[redis.Redis, Depends(get_redis)],
    limit: Annotated[int, Query(ge=1)] = 10,
) -> list[SimilarGameItem]:
    """Return personalized game recommendations for the current client.

    Pipeline:
        1. Compute ``exclude_game_ids`` from the client's open orders:
           games they already have or will receive are not recommended.
        2. Call the recommendation gRPC service with ``limit * 3`` as
           an over-fetch, so the availability filter does not starve
           the response.
        3. Post-filter by availability: drop games with no free copy
           anywhere (all copies rented out, in transit or with a client).
        4. Trim to ``limit``.
    """
    exclude_ids = await order_crud.get_active_game_ids(session, client.id)

    recs = await recommendation_client.get_personal_recommendations(
        client_id=client.id,
        exclude_game_ids=exclude_ids,
        limit=limit * 3,
    )
    if not recs:
        return await _fallback_popular(
            session, redis_client, exclude_ids, limit,
        )

    candidate_ids = [r.game_id for r in recs]
    free_copies = await game_copy.count_free(session, candidate_ids)
    available_ids = {g for (g, _) in free_copies.keys()}

    filtered = [r for r in recs if r.game_id in available_ids][:limit]
    if not filtered:
        return await _fallback_popular(
            session, redis_client, exclude_ids, limit,
        )

    from app.crud import board_game
    from app.schemas import BoardGameRead

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


async def _fallback_popular(
    session: AsyncSession,
    redis_client: redis.Redis,
    exclude_ids: list[int],
    limit: int,
) -> list[SimilarGameItem]:
    """Return popular catalog games, filtered by availability."""
    games = await catalog_cache.list_games(
        redis_client, session, limit=limit * 3,
    )
    if not games:
        return []

    candidate_ids = [g.id for g in games if g.id not in exclude_ids]
    free_copies = await game_copy.count_free(session, candidate_ids)
    available_ids = {g for (g, _) in free_copies.keys()}

    result: list[SimilarGameItem] = []
    for g in games:
        if g.id in exclude_ids or g.id not in available_ids:
            continue
        result.append(SimilarGameItem(game=g, reason="fallback_popular"))
        if len(result) >= limit:
            break
    return result