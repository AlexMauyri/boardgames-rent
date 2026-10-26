"""Tests for the scaffolded gRPC service."""

import grpc
import pytest
from grpc_health.v1 import health_pb2, health_pb2_grpc

from app.generated.recommendation.v1 import (
    recommendation_pb2,
    recommendation_pb2_grpc,
)


async def test_health_reports_serving(grpc_server):
    async with grpc.aio.insecure_channel(f"localhost:{grpc_server}") as channel:
        stub = health_pb2_grpc.HealthStub(channel)
        resp = await stub.Check(health_pb2.HealthCheckRequest(), timeout=2.0)
    assert resp.status == health_pb2.HealthCheckResponse.SERVING


async def test_get_similar_games_is_unimplemented(grpc_server):
    async with grpc.aio.insecure_channel(f"localhost:{grpc_server}") as channel:
        stub = recommendation_pb2_grpc.RecommendationServiceStub(channel)
        with pytest.raises(grpc.aio.AioRpcError) as exc:
            await stub.GetSimilarGames(
                recommendation_pb2.GetSimilarGamesRequest(target_game_id=1),
                timeout=2.0,
            )
    assert exc.value.code() == grpc.StatusCode.UNIMPLEMENTED


async def test_get_personal_recommendations_is_unimplemented(grpc_server):
    async with grpc.aio.insecure_channel(f"localhost:{grpc_server}") as channel:
        stub = recommendation_pb2_grpc.RecommendationServiceStub(channel)
        with pytest.raises(grpc.aio.AioRpcError) as exc:
            await stub.GetPersonalRecommendations(
                recommendation_pb2.GetPersonalRecommendationsRequest(
                    client_id=1,
                ),
                timeout=2.0,
            )
    assert exc.value.code() == grpc.StatusCode.UNIMPLEMENTED