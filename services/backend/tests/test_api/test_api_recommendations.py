"""Tests for GET /recommendations/personal."""

from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.auth.jwt import create_access_token
from app.db.models import Order
from app.grpc_generated.recommendation.v1 import recommendation_pb2
from app.main import app as fastapi_app
from app.schemas import OrderCreate
from app.services.orders import create_order
from tests.helpers import make_client, make_copy, make_game, make_point


def _headers(client_id: int) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(client_id, 'CLIENT')}"}


def _rec(game_id: int, reason: str = "bought_together") -> recommendation_pb2.GameRecommendation:
    return recommendation_pb2.GameRecommendation(
        game_id=game_id, score=0.9, reason=reason,
    )


@pytest.fixture
def mock_grpc():
    mock = MagicMock()
    mock.get_personal_recommendations = AsyncMock(return_value=[])
    fastapi_app.state.recommendation_client = mock
    return mock


async def test_personal_requires_auth(http):
    r = await http.get("/api/v1/recommendations/personal")
    assert r.status_code == 401


async def test_personal_empty_grpc_falls_back_to_popular(http, session, mock_grpc):
    client_id = await make_client(session)
    point_id = await make_point(session)
    game_id = await make_game(session)
    await make_copy(session, game_id, point_id, "I1")
    mock_grpc.get_personal_recommendations.return_value = []

    r = await http.get(
        "/api/v1/recommendations/personal", headers=_headers(client_id),
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body) > 0
    assert body[0]["reason"] == "fallback_popular"
    assert body[0]["game"]["id"] == game_id


async def test_personal_active_orders_excluded(http, session, mock_grpc):
    client_id = await make_client(session)
    point_id = await make_point(session)
    game_id = await make_game(session)
    await make_copy(session, game_id, point_id, "I1")

    order = await create_order(session, client_id, OrderCreate(
        pickup_point_id=point_id,
        start_date=date.today() + timedelta(days=1),
        end_date=date.today() + timedelta(days=2),
        game_ids=[game_id],
    ))
    row = await session.get(Order, order.id)
    row.status = "ACTIVE"
    await session.commit()

    mock_grpc.get_personal_recommendations.return_value = [_rec(game_id)]

    r = await http.get(
        "/api/v1/recommendations/personal", headers=_headers(client_id),
    )
    assert r.status_code == 200
    ids = [item["game"]["id"] for item in r.json()]
    assert game_id not in ids


async def test_personal_happy_path(http, session, mock_grpc):
    client_id = await make_client(session)
    point_id = await make_point(session)
    game1 = await make_game(session, "G1")
    game2 = await make_game(session, "G2")
    await make_copy(session, game2, point_id, "I2")  # game1 has no copy

    mock_grpc.get_personal_recommendations.return_value = [_rec(game1), _rec(game2)]

    r = await http.get(
        "/api/v1/recommendations/personal", headers=_headers(client_id),
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["game"]["id"] == game2
    assert body[0]["reason"] == "bought_together"


async def test_personal_overfetch_multiplier(http, session, mock_grpc):
    client_id = await make_client(session)
    await http.get(
        "/api/v1/recommendations/personal?limit=4", headers=_headers(client_id),
    )
    mock_grpc.get_personal_recommendations.assert_called_once_with(
        client_id=client_id,
        exclude_game_ids=[],
        limit=12,
    )


async def test_personal_grpc_error_returns_fallback(http, session, mock_grpc):
    client_id = await make_client(session)
    point_id = await make_point(session)
    game_id = await make_game(session)
    await make_copy(session, game_id, point_id, "I1")

    mock_grpc.get_personal_recommendations.return_value = []

    r = await http.get(
        "/api/v1/recommendations/personal", headers=_headers(client_id),
    )
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.json()[0]["reason"] == "fallback_popular"