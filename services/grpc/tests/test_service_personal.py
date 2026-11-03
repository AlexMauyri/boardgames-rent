"""Integration tests for GetPersonalRecommendations."""

import grpc
import pytest
from sqlalchemy import text

from app.generated.recommendation.v1 import (
    recommendation_pb2,
    recommendation_pb2_grpc,
)


async def _seed(session) -> None:
    """Seed a small catalog and three clients.

    Games:
        G1 (C1), G2 (C2), G3 (C3), G4 (C1), G5 (C3), G6 (C4), G7 (C1)

    Alice (client 1) — history:
        O1 COMPLETED: G1, G2
        O2 COMPLETED: G1, G3

    Bob (client 2) — contributed orders:
        O3 COMPLETED: G1, G4
        O4 COMPLETED: G2, G5
        O5 COMPLETED: G4, G7

    Charlie (client 3) — no orders at all.

    Alice's CF candidates (co-occurrence partners outside her history):
        From G1 → {G2, G3, G4} → keep G4 (cooc=1)
        From G2 → {G1, G5}     → keep G5 (cooc=1)
        From G3 → {G1}         → nothing

    So Alice should get {G4, G5} with reason "bought_together".

    G7 is popular (in O5) and in C1 (a history category), but never
    co-occurs with Alice's games. It shows up only via the fallback
    when G4 and G5 are excluded.
    """
    await session.execute(text(
        "INSERT INTO app.pickup_points (id, name, address, phone) "
        "VALUES (1, 'P1', 'addr', '+7')"
    ))
    await session.execute(text(
        "INSERT INTO app.clients "
        "(id, email, password_hash, full_name, phone) VALUES "
        "(1, 'alice@t.io',   'h', 'Alice',   '+7'), "
        "(2, 'bob@t.io',     'h', 'Bob',     '+7'), "
        "(3, 'charlie@t.io', 'h', 'Charlie', '+7')"
    ))
    await session.execute(text(
        "INSERT INTO app.board_games "
        "(id, title, min_players, max_players, playtime_minutes, "
        " daily_price, deposit_price) VALUES "
        "(1, 'G1', 1, 4, 60, 10, 100), "
        "(2, 'G2', 1, 4, 60, 10, 100), "
        "(3, 'G3', 1, 4, 60, 10, 100), "
        "(4, 'G4', 1, 4, 60, 10, 100), "
        "(5, 'G5', 1, 4, 60, 10, 100), "
        "(6, 'G6', 1, 4, 60, 10, 100), "
        "(7, 'G7', 1, 4, 60, 10, 100)"
    ))
    await session.execute(text(
        "INSERT INTO app.categories (id, name) VALUES "
        "(1, 'C1'), (2, 'C2'), (3, 'C3'), (4, 'C4')"
    ))
    await session.execute(text(
        "INSERT INTO app.game_categories (game_id, category_id) VALUES "
        "(1, 1), (2, 2), (3, 3), "
        "(4, 1), (5, 3), (6, 4), (7, 1)"
    ))
    await session.execute(text(
        "INSERT INTO app.game_copies "
        "(id, game_id, current_point_id, inventory_number, status) VALUES "
        "(1, 1, 1, 'I1', 'AVAILABLE'), "
        "(2, 2, 1, 'I2', 'AVAILABLE'), "
        "(3, 3, 1, 'I3', 'AVAILABLE'), "
        "(4, 4, 1, 'I4', 'AVAILABLE'), "
        "(5, 5, 1, 'I5', 'AVAILABLE'), "
        "(6, 6, 1, 'I6', 'AVAILABLE'), "
        "(7, 7, 1, 'I7', 'AVAILABLE')"
    ))
    await session.execute(text(
        "INSERT INTO app.orders "
        "(id, client_id, pickup_point_id, start_date, end_date, "
        " total_price, deposit_paid, status, created_at) VALUES "
        "(1, 1, 1, '2026-01-01', '2026-01-02', 10, 100, 'COMPLETED', '2026-01-02'), "
        "(2, 1, 1, '2026-01-03', '2026-01-04', 10, 100, 'COMPLETED', '2026-01-04'), "
        "(3, 2, 1, '2026-01-05', '2026-01-06', 10, 100, 'COMPLETED', '2026-01-06'), "
        "(4, 2, 1, '2026-01-07', '2026-01-08', 10, 100, 'COMPLETED', '2026-01-08'), "
        "(5, 2, 1, '2026-01-09', '2026-01-10', 10, 100, 'COMPLETED', '2026-01-10')"
    ))
    await session.execute(text(
        "INSERT INTO app.order_items (order_id, game_copy_id, price_at_rental) VALUES "
        "(1, 1, 10), (1, 2, 10), "
        "(2, 1, 10), (2, 3, 10), "
        "(3, 1, 10), (3, 4, 10), "
        "(4, 2, 10), (4, 5, 10), "
        "(5, 4, 10), (5, 7, 10)"
    ))
    await session.commit()


@pytest.fixture
async def seeded(app_session):
    await _seed(app_session)
    return app_session


async def _call(
    port: int,
    request: recommendation_pb2.GetPersonalRecommendationsRequest,
):
    async with grpc.aio.insecure_channel(f"localhost:{port}") as channel:
        stub = recommendation_pb2_grpc.RecommendationServiceStub(channel)
        return await stub.GetPersonalRecommendations(request, timeout=5.0)


async def test_personal_with_history_uses_cf(grpc_server, seeded):
    """Alice gets G4 and G5 from co-occurrence with her history."""
    response = await _call(grpc_server, recommendation_pb2.GetPersonalRecommendationsRequest(
        client_id=1, limit=10,
    ))
    ids = {r.game_id for r in response.games}
    assert ids == {4, 5}
    assert all(r.reason == "bought_together" for r in response.games)


async def test_personal_excludes_history(grpc_server, seeded):
    response = await _call(grpc_server, recommendation_pb2.GetPersonalRecommendationsRequest(
        client_id=1, limit=10,
    ))
    ids = {r.game_id for r in response.games}
    assert 1 not in ids
    assert 2 not in ids
    assert 3 not in ids


async def test_personal_respects_exclude_list(grpc_server, seeded):
    """Excluding G4 leaves only G5 from the CF candidates."""
    response = await _call(grpc_server, recommendation_pb2.GetPersonalRecommendationsRequest(
        client_id=1, exclude_game_ids=[4], limit=10,
    ))
    ids = {r.game_id for r in response.games}
    assert ids == {5}


async def test_personal_empty_history_falls_back_to_popular(grpc_server, seeded):
    """Charlie has no completed orders; response is fallback_popular."""
    response = await _call(grpc_server, recommendation_pb2.GetPersonalRecommendationsRequest(
        client_id=3, limit=10,
    ))
    assert len(response.games) > 0
    assert all(r.reason == "fallback_popular" for r in response.games)


async def test_personal_respects_limit(grpc_server, seeded):
    response = await _call(grpc_server, recommendation_pb2.GetPersonalRecommendationsRequest(
        client_id=1, limit=1,
    ))
    assert len(response.games) == 1


async def test_personal_all_cf_excluded_falls_back(grpc_server, seeded):
    """Excluding G4 and G5 forces the fallback path.

    G7 is popular (ordered by Bob) and lives in C1 (a history category),
    so it should appear in the fallback even though it never co-occurs
    with Alice's games.
    """
    response = await _call(grpc_server, recommendation_pb2.GetPersonalRecommendationsRequest(
        client_id=1, exclude_game_ids=[4, 5], limit=10,
    ))
    assert len(response.games) > 0
    assert all(r.reason == "fallback_popular" for r in response.games)
    assert 7 in {r.game_id for r in response.games}