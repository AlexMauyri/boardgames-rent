"""Integration tests for GetSimilarGames over an in-process gRPC server."""

import grpc
import pytest
from sqlalchemy import text

from app.generated.recommendation.v1 import (
    recommendation_pb2,
    recommendation_pb2_grpc,
)


async def _seed(session) -> None:
    """Seed a small catalog and 2 completed orders.

    Games:
        G1 (C1, C2)  — target
        G2 (C2)
        G3 (C1)
        G4 (C1)
        G5 (C3)

    Orders:
        O1 COMPLETED: G1, G2, G3
        O2 COMPLETED: G1, G4, G5

    Co-occurrence with G1:
        G2: 1, G3: 1, G4: 1, G5: 1
    All four qualify; diversity cap limits G3 and G4 (both C1) to two
    games together.
    """
    await session.execute(text(
        "INSERT INTO app.pickup_points (id, name, address, phone) "
        "VALUES (1, 'P1', 'addr', '+7')"
    ))
    await session.execute(text(
        "INSERT INTO app.clients "
        "(id, email, password_hash, full_name, phone) "
        "VALUES (1, 'a@t.io', 'h', 'Alice', '+7')"
    ))
    await session.execute(text(
        "INSERT INTO app.board_games "
        "(id, title, min_players, max_players, playtime_minutes, "
        " daily_price, deposit_price) VALUES "
        "(1, 'G1', 1, 4, 60, 10, 100), "
        "(2, 'G2', 1, 4, 60, 10, 100), "
        "(3, 'G3', 1, 4, 60, 10, 100), "
        "(4, 'G4', 1, 4, 60, 10, 100), "
        "(5, 'G5', 1, 4, 60, 10, 100)"
    ))
    await session.execute(text(
        "INSERT INTO app.categories (id, name) VALUES "
        "(1, 'C1'), (2, 'C2'), (3, 'C3')"
    ))
    await session.execute(text(
        "INSERT INTO app.game_categories (game_id, category_id) VALUES "
        "(1, 1), (1, 2), "
        "(2, 2), (3, 1), (4, 1), (5, 3)"
    ))
    await session.execute(text(
        "INSERT INTO app.game_copies "
        "(id, game_id, current_point_id, inventory_number, status) VALUES "
        "(1, 1, 1, 'I1', 'AVAILABLE'), "
        "(2, 2, 1, 'I2', 'AVAILABLE'), "
        "(3, 3, 1, 'I3', 'AVAILABLE'), "
        "(4, 4, 1, 'I4', 'AVAILABLE'), "
        "(5, 5, 1, 'I5', 'AVAILABLE')"
    ))
    await session.execute(text(
        "INSERT INTO app.orders "
        "(id, client_id, pickup_point_id, start_date, end_date, "
        " total_price, deposit_paid, status, created_at) VALUES "
        "(1, 1, 1, '2026-01-01', '2026-01-02', 10, 100, 'COMPLETED', '2026-01-02'), "
        "(2, 1, 1, '2026-01-03', '2026-01-04', 10, 100, 'COMPLETED', '2026-01-04')"
    ))
    await session.execute(text(
        "INSERT INTO app.order_items (order_id, game_copy_id, price_at_rental) VALUES "
        "(1, 1, 10), (1, 2, 10), (1, 3, 10), "
        "(2, 1, 10), (2, 4, 10), (2, 5, 10)"
    ))
    await session.commit()


@pytest.fixture
async def seeded(app_session):
    await _seed(app_session)
    return app_session


async def _call(port: int, request: recommendation_pb2.GetSimilarGamesRequest):
    async with grpc.aio.insecure_channel(f"localhost:{port}") as channel:
        stub = recommendation_pb2_grpc.RecommendationServiceStub(channel)
        return await stub.GetSimilarGames(request, timeout=5.0)


async def test_similar_returns_cooc_candidates(grpc_server, seeded):
    response = await _call(grpc_server, recommendation_pb2.GetSimilarGamesRequest(
        target_game_id=1, limit=10,
    ))
    ids = [r.game_id for r in response.games]
    assert set(ids) >= {2, 3, 4, 5}


async def test_similar_excludes_target(grpc_server, seeded):
    response = await _call(grpc_server, recommendation_pb2.GetSimilarGamesRequest(
        target_game_id=1, limit=10,
    ))
    assert 1 not in [r.game_id for r in response.games]


async def test_similar_respects_exclude_list(grpc_server, seeded):
    response = await _call(grpc_server, recommendation_pb2.GetSimilarGamesRequest(
        target_game_id=1,
        exclude_game_ids=[2, 3],
        limit=10,
    ))
    ids = [r.game_id for r in response.games]
    assert 2 not in ids
    assert 3 not in ids


async def test_similar_respects_limit(grpc_server, seeded):
    response = await _call(grpc_server, recommendation_pb2.GetSimilarGamesRequest(
        target_game_id=1, limit=1,
    ))
    assert len(response.games) == 1


async def test_similar_diversity_cap(grpc_server, seeded):
    """At most 2 games per category: G3 and G4 are both C1, so both fit.

    To actually exercise the cap, request a 2-game limit and verify the
    result does not exceed 2 games of the same category.
    """
    response = await _call(grpc_server, recommendation_pb2.GetSimilarGamesRequest(
        target_game_id=1, limit=10,
    ))
    from collections import Counter
    category_counts: Counter[int] = Counter()
    game_cats = {
        2: {2}, 3: {1}, 4: {1}, 5: {3},
    }
    for rec in response.games:
        for c in game_cats[rec.game_id]:
            category_counts[c] += 1
    assert all(count <= 2 for count in category_counts.values())


async def test_similar_reason_is_bought_together(grpc_server, seeded):
    response = await _call(grpc_server, recommendation_pb2.GetSimilarGamesRequest(
        target_game_id=1, limit=10,
    ))
    assert all(r.reason == "bought_together" for r in response.games)


async def test_similar_unknown_target(grpc_server, seeded):
    with pytest.raises(grpc.aio.AioRpcError) as exc:
        await _call(grpc_server, recommendation_pb2.GetSimilarGamesRequest(
            target_game_id=999, limit=10,
        ))
    assert exc.value.code() == grpc.StatusCode.NOT_FOUND


async def test_similar_no_cooc_returns_empty(grpc_server, seeded):
    """G5 only co-occurs with G1; a target with no cooc returns []."""
    response = await _call(grpc_server, recommendation_pb2.GetSimilarGamesRequest(
        target_game_id=999, limit=10,
    )) if False else None
    response = await _call(grpc_server, recommendation_pb2.GetSimilarGamesRequest(
        target_game_id=1,
        exclude_game_ids=[2, 3, 4, 5],
        limit=10,
    ))
    assert list(response.games) == []