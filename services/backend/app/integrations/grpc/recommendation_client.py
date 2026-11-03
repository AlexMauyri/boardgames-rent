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
    """Holds a single TLS channel and a typed stub for the service."""

    def __init__(self) -> None:
        self._channel: grpc.aio.Channel | None = None
        self._stub: recommendation_pb2_grpc.RecommendationServiceStub | None = None

    async def start(self) -> None:
        """Open the TLS channel and create the stub."""
        with open(settings.grpc_ca_cert_path, "rb") as f:
            trusted_certs = f.read()

        credentials = grpc.ssl_channel_credentials(
            root_certificates=trusted_certs,
        )
        self._channel = grpc.aio.secure_channel(
            settings.grpc_recommendation_addr, credentials,
        )
        self._stub = recommendation_pb2_grpc.RecommendationServiceStub(
            self._channel,
        )
        logger.info(
            "recommendation gRPC client ready: %s",
            settings.grpc_recommendation_addr,
        )

    async def close(self) -> None:
        """Close the channel. Called on shutdown."""
        if self._channel is not None:
            await self._channel.close()
            self._channel = None
            self._stub = None

    async def get_similar_games(
        self,
        target_game_id: int,
        exclude_game_ids: list[int],
        limit: int = 10,
    ) -> list[recommendation_pb2.GameRecommendation]:
        """Call GetSimilarGames; return [] on any gRPC error."""
        if self._stub is None:
            return []

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
        if self._stub is None:
            return []

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