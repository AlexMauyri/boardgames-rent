"""Recommendation services: similar games and personal recommendations.

Coordinates between the recommendation gRPC client, PostgreSQL (for
availability and catalog data) and Redis (for fallback caching).
"""

import logging

import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import board_game, game_copy
from app.crud import order as order_crud
from app.integrations.grpc.recommendation_client import RecommendationClient
from app.schemas import BoardGameRead, SimilarGameItem
from app.services import catalog_cache
from app.services.exceptions import NotFoundError

logger = logging.getLogger(__name__)


async def get_similar_games(
    session: AsyncSession,
    recommendation_client: RecommendationClient,
    game_id: int,
    limit: int,
) -> list[SimilarGameItem]:
    """Return games similar to ``game_id``, filtered by availability.

    Args:
        session: Active async session.
        recommendation_client: gRPC client for recommendations.
        game_id: Target board game id.
        limit: Maximum number of games to return.

    Returns:
        Games similar to the target, available for rent, with reasons.

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
        logger.info("similar games empty target=%s", game_id)
        return []

    candidate_ids = [r.game_id for r in recs]
    free_copies = await game_copy.count_free(session, candidate_ids)
    available_ids = {g for (g, _) in free_copies.keys()}

    filtered = [r for r in recs if r.game_id in available_ids][:limit]
    if not filtered:
        logger.info("similar games unavailable after filter target=%s", game_id)
        return []

    games = await board_game.get_many(session, [r.game_id for r in filtered])
    games_by_id = {g.id: g for g in games}

    result = [
        SimilarGameItem(
            game=BoardGameRead.model_validate(games_by_id[r.game_id]),
            reason=r.reason,
        )
        for r in filtered
        if r.game_id in games_by_id
    ]

    logger.info(
        "similar games found target=%s count=%s",
        game_id, len(result),
    )
    return result


async def get_personal_recommendations(
    session: AsyncSession,
    redis_client: redis.Redis,
    recommendation_client: RecommendationClient,
    client_id: int,
    limit: int,
) -> list[SimilarGameItem]:
    """Return personalized recommendations for the given client.

    Args:
        session: Active async session.
        redis_client: Redis client for fallback cache.
        recommendation_client: gRPC client for recommendations.
        client_id: Client id.
        limit: Maximum number of games to return.

    Returns:
        Recommended games, available for rent.
    """
    exclude_ids = await order_crud.get_active_game_ids(session, client_id)

    # Over-fetch to survive the availability post-filter
    recs = await recommendation_client.get_personal_recommendations(
        client_id=client_id,
        exclude_game_ids=exclude_ids,
        limit=limit * 3,
    )
    if not recs:
        logger.info("personal recs empty client=%s, using fallback", client_id)
        return await _fallback_popular(
            session, redis_client, exclude_ids, limit,
        )

    candidate_ids = [r.game_id for r in recs]
    free_copies = await game_copy.count_free(session, candidate_ids)
    available_ids = {g for (g, _) in free_copies.keys()}

    filtered = [r for r in recs if r.game_id in available_ids][:limit]
    if not filtered:
        logger.info("personal recs unavailable client=%s, using fallback", client_id)
        return await _fallback_popular(
            session, redis_client, exclude_ids, limit,
        )

    games = await board_game.get_many(session, [r.game_id for r in filtered])
    games_by_id = {g.id: g for g in games}

    result = [
        SimilarGameItem(
            game=BoardGameRead.model_validate(games_by_id[r.game_id]),
            reason=r.reason,
        )
        for r in filtered
        if r.game_id in games_by_id
    ]

    logger.info(
        "personal recs found client=%s count=%s",
        client_id, len(result),
    )
    return result


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