"""Tests for the recommendation gRPC client."""

import pytest

from app.integrations.grpc.recommendation_client import RecommendationClient
from app.integrations.grpc.channel import open_secure_channel
from app.config import settings


@pytest.fixture
async def broken_client(monkeypatch):
    """Client pointed at a closed port so the first RPC fails fast."""
    monkeypatch.setattr(
        settings, "grpc_service_addr", "127.0.0.1:1",
    )
    monkeypatch.setattr(settings, "grpc_timeout_seconds", 0.2)
    channel = open_secure_channel()
    client = RecommendationClient(channel)
    yield client
    await channel.close()


async def test_similar_returns_empty_when_server_unreachable(broken_client):
    result = await broken_client.get_similar_games(
        target_game_id=1, exclude_game_ids=[], limit=10,
    )
    assert result == []


async def test_personal_returns_empty_when_server_unreachable(broken_client):
    result = await broken_client.get_personal_recommendations(
        client_id=1, exclude_game_ids=[], limit=10,
    )
    assert result == []
