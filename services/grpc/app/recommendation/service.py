"""gRPC recommendation servicer."""

import grpc

from app.generated.recommendation.v1 import (
    recommendation_pb2,
    recommendation_pb2_grpc,
)


class RecommendationServicer(
    recommendation_pb2_grpc.RecommendationServiceServicer,
):
    """Serves RecommendationService."""

    async def GetSimilarGames(
        self,
        request: recommendation_pb2.GetSimilarGamesRequest,
        context: grpc.aio.ServicerContext,
    ) -> recommendation_pb2.GetSimilarGamesResponse:
        await context.abort(
            grpc.StatusCode.UNIMPLEMENTED,
            "GetSimilarGames is not implemented yet",
        )

    async def GetPersonalRecommendations(
        self,
        request: recommendation_pb2.GetPersonalRecommendationsRequest,
        context: grpc.aio.ServicerContext,
    ) -> recommendation_pb2.GetPersonalRecommendationsResponse:
        await context.abort(
            grpc.StatusCode.UNIMPLEMENTED,
            "GetPersonalRecommendations is not implemented yet",
        )