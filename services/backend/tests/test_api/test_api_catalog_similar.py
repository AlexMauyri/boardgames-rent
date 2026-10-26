"""Tests for GET /catalog/games/{id}/similar.

The gRPC client is replaced with an ``AsyncMock`` via app.state; the
database is the real test database seeded with small fixtures. Availability
filtering is exercised by inserting copies with statuses that make games
unavailable.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.grpc_generated.recommendation.v1 import recommendation_pb2
from app.main import app as fastapi_app
from tests.helpers import make_copy, make_game, make_point


def _rec(game_id: int, reason: str = "bought_together") -> recommendation_pb2.GameRecommendation:
    return recommendation_pb2.GameRecommendation(
        game_id=game_id, score=0.9, reason=reason,
    )


@pytest.fixture
def mock_grpc():
    """Install a MagicMock on app.state and reset it between tests."""
    mock = MagicMock()
    mock.get_similar_games = AsyncMock(return_value=[])
    fastapi_app.state.recommendation_client = mock
    return mock


async def test_similar_unknown_game_404(http, session, mock_grpc):
    r = await http.get("/api/v1/catalog/games/999999/similar")
    assert r.status_code == 404
    mock_grpc.get_similar_games.assert_not_called()


async def test_similar_empty_grpc_returns_empty(http, session, mock_grpc):
    game_id = await make_game(session)
    mock_grpc.get_similar_games.return_value = []

    r = await http.get(f"/api/v1/catalog/games/{game_id}/similar")

    assert r.status_code == 200
    assert r.json() == []


async def test_similar_filters_unavailable(http, session, mock_grpc):
    """Games with no AVAILABLE copy are filtered out."""
    target = await make_game(session, "Target")
    avail = await make_game(session, "Available")
    lost = await make_game(session, "Lost")
    point = await make_point(session)

    await make_copy(session, avail, point, "I1")
    # 'Lost' has a copy, but it is with a client, not on a shelf.
    await make_copy(session, lost, None, "I2", status="WITH_CLIENT")

    mock_grpc.get_similar_games.return_value = [_rec(avail), _rec(lost)]

    r = await http.get(f"/api/v1/catalog/games/{target}/similar")

    assert r.status_code == 200
    body = r.json()
    assert [item["game"]["id"] for item in body] == [avail]
    assert body[0]["reason"] == "bought_together"


async def test_similar_trims_to_limit(http, session, mock_grpc):
    target = await make_game(session, "Target")
    point = await make_point(session)
    ids = []
    for i in range(5):
        gid = await make_game(session, f"G{i}")
        await make_copy(session, gid, point, f"INV-{i}")
        ids.append(gid)

    mock_grpc.get_similar_games.return_value = [_rec(gid) for gid in ids]

    r = await http.get(f"/api/v1/catalog/games/{target}/similar?limit=2")

    assert r.status_code == 200
    assert len(r.json()) == 2


async def test_similar_overfetch_multiplier(http, session, mock_grpc):
    """Endpoint asks gRPC for limit * 3 candidates."""
    game_id = await make_game(session)

    await http.get(f"/api/v1/catalog/games/{game_id}/similar?limit=4")

    mock_grpc.get_similar_games.assert_called_once_with(
        target_game_id=game_id,
        exclude_game_ids=[game_id],
        limit=12,
    )


async def test_similar_grpc_error_returns_empty(http, session, mock_grpc):
    """If the gRPC client returns [] (its own failure handling), 200 + []."""
    game_id = await make_game(session)
    mock_grpc.get_similar_games.return_value = []

    r = await http.get(f"/api/v1/catalog/games/{game_id}/similar")

    assert r.status_code == 200
    assert r.json() == []