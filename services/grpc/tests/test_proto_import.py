"""Verify the generated proto stubs are importable and well-formed."""

from app.generated.recommendation.v1 import (
    recommendation_pb2,
    recommendation_pb2_grpc,
)


def test_messages_exist():
    assert hasattr(recommendation_pb2, "GameRecommendation")
    assert hasattr(recommendation_pb2, "GetSimilarGamesRequest")
    assert hasattr(recommendation_pb2, "GetSimilarGamesResponse")
    assert hasattr(recommendation_pb2, "GetPersonalRecommendationsRequest")
    assert hasattr(recommendation_pb2, "GetPersonalRecommendationsResponse")


def test_stub_exists():
    assert hasattr(recommendation_pb2_grpc, "RecommendationServiceStub")
    assert hasattr(recommendation_pb2_grpc, "RecommendationServiceServicer")
    assert hasattr(recommendation_pb2_grpc, "add_RecommendationServiceServicer_to_server")


def test_similar_request_round_trip():
    req = recommendation_pb2.GetSimilarGamesRequest(
        target_game_id=42,
        exclude_game_ids=[1, 2, 3],
        limit=10,
    )
    serialized = req.SerializeToString()
    parsed = recommendation_pb2.GetSimilarGamesRequest()
    parsed.ParseFromString(serialized)

    assert parsed.target_game_id == 42
    assert list(parsed.exclude_game_ids) == [1, 2, 3]
    assert parsed.limit == 10


def test_personal_request_round_trip():
    req = recommendation_pb2.GetPersonalRecommendationsRequest(
        client_id=7,
        exclude_game_ids=[5],
        limit=20,
    )
    parsed = recommendation_pb2.GetPersonalRecommendationsRequest()
    parsed.ParseFromString(req.SerializeToString())

    assert parsed.client_id == 7
    assert list(parsed.exclude_game_ids) == [5]
    assert parsed.limit == 20


def test_game_recommendation_defaults():
    rec = recommendation_pb2.GameRecommendation()
    assert rec.game_id == 0
    assert rec.score == 0.0
    assert rec.reason == ""