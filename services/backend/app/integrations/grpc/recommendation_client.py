"""Client for the recommendation gRPC service."""

import logging

import grpc
import grpc.aio

from app.config import settings
from app.grpc_generated.recommendation.v1 import (
    recommendation_pb2,
    recommendation_pb2_grpc,
)

logger = logging.getLogger(__name__)


class RecommendationClient:
    """Typed stub for ``RecommendationService`` over a shared channel."""

    def __init__(self, channel: grpc.aio.Channel) -> None:
        self._stub = recommendation_pb2_grpc.RecommendationServiceStub(channel)

    async def get_similar_games(
        self,
        target_game_id: int,
        exclude_game_ids: list[int],
        limit: int = 10,
    ) -> list[recommendation_pb2.GameRecommendation]:
        """Call GetSimilarGames; return [] on any gRPC error."""
        request = recommendation_pb2.GetSimilarGamesRequest(
            target_game_id=target_game_id,
            exclude_game_ids=exclude_game_ids,
            limit=limit,
        )
        try:
            response = await self._stub.GetSimilarGames(
                request, timeout=settings.grpc_timeout_seconds,
            )
            return list(response.games)
        except grpc.aio.AioRpcError as exc:
            logger.warning(
                "gRPC GetSimilarGames failed target=%s code=%s",
                target_game_id, exc.code(),
            )
            return []

    async def get_personal_recommendations(
        self,
        client_id: int,
        exclude_game_ids: list[int],
        limit: int = 10,
    ) -> list[recommendation_pb2.GameRecommendation]:
        """Call GetPersonalRecommendations; return [] on any gRPC error."""
        request = recommendation_pb2.GetPersonalRecommendationsRequest(
            client_id=client_id,
            exclude_game_ids=exclude_game_ids,
            limit=limit,
        )
        try:
            response = await self._stub.GetPersonalRecommendations(
                request, timeout=settings.grpc_timeout_seconds,
            )
            return list(response.games)
        except grpc.aio.AioRpcError as exc:
            logger.warning(
                "gRPC GetPersonalRecommendations failed client=%s code=%s",
                client_id, exc.code(),
            )
            return []