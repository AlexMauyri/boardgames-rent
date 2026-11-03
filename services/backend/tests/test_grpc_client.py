"""Tests for the recommendation gRPC client."""

import pytest

from app.integrations.grpc.recommendation_client import RecommendationClient
from app.config import settings


@pytest.fixture
def broken_client(monkeypatch):
    """Client pointed at a closed port so the first RPC fails fast."""
    monkeypatch.setattr(
        settings, "grpc_recommendation_addr", "127.0.0.1:1",
    )
    monkeypatch.setattr(settings, "grpc_timeout_seconds", 0.2)
    return RecommendationClient()


async def test_similar_returns_empty_when_server_unreachable(broken_client):
    await broken_client.start()
    try:
        result = await broken_client.get_similar_games(
            target_game_id=1, exclude_game_ids=[], limit=10,
        )
    finally:
        await broken_client.close()
    assert result == []


async def test_personal_returns_empty_when_server_unreachable(broken_client):
    await broken_client.start()
    try:
        result = await broken_client.get_personal_recommendations(
            client_id=1, exclude_game_ids=[], limit=10,
        )
    finally:
        await broken_client.close()
    assert result == []


async def test_client_before_start_returns_empty():
    """Methods on a non-started client return [] without raising."""
    client = RecommendationClient()
    assert await client.get_similar_games(1, []) == []
    assert await client.get_personal_recommendations(1, []) == []