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
from app.db.models import Client
from app.integrations.grpc.recommendation_client import RecommendationClient
from app.schemas import SimilarGameItem
from app.services import recommendations as recommendations_service

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
    """Return personalized game recommendations for the current client."""
    return await recommendations_service.get_personal_recommendations(
        session, redis_client, recommendation_client, client.id, limit,
    )