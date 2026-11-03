"""Integration tests for the recommendation repository."""

import pytest
from sqlalchemy import text

from app.recommendation.repository import (
    get_client_history,
    get_cooccurrence,
    get_game_content,
    get_popularity,
    get_top_popular,
)


# ---------------------------------------------------------------------------
# Fixture data
#
# Games:     G1 (cats 1,2), G2 (cats 2), G3 (cats 3), G4 (cats 1)
# Clients:   Alice (1), Bob (2)
# Orders:
#   O1 COMPLETED (Alice): G1, G2
#   O2 COMPLETED (Bob):   G2, G3
#   O3 COMPLETED (Alice): G1, G4
#   O4 CANCELLED (Alice): G3   ← must be ignored everywhere
# ---------------------------------------------------------------------------


async def _seed(session) -> None:
    await session.execute(text(
        "INSERT INTO app.pickup_points (id, name, address, phone) "
        "VALUES (1, 'P1', 'addr', '+7')"
    ))
    await session.execute(text(
        "INSERT INTO app.clients "
        "(id, email, password_hash, full_name, phone) VALUES "
        "(1, 'a@t.io', 'h', 'Alice', '+7'), "
        "(2, 'b@t.io', 'h', 'Bob',   '+7')"
    ))
    await session.execute(text(
        "INSERT INTO app.board_games "
        "(id, title, min_players, max_players, playtime_minutes, "
        " daily_price, deposit_price) VALUES "
        "(1, 'G1', 1, 4, 60, 10, 100), "
        "(2, 'G2', 1, 4, 60, 10, 100), "
        "(3, 'G3', 1, 4, 60, 10, 100), "
        "(4, 'G4', 1, 4, 60, 10, 100)"
    ))
    await session.execute(text(
        "INSERT INTO app.categories (id, name) VALUES "
        "(1, 'C1'), (2, 'C2'), (3, 'C3')"
    ))
    await session.execute(text(
        "INSERT INTO app.game_categories (game_id, category_id) VALUES "
        "(1, 1), (1, 2), (2, 2), (3, 3), (4, 1)"
    ))
    await session.execute(text(
        "INSERT INTO app.game_copies "
        "(id, game_id, current_point_id, inventory_number, status) VALUES "
        "(1, 1, 1, 'I1', 'AVAILABLE'), "
        "(2, 2, 1, 'I2', 'AVAILABLE'), "
        "(3, 3, 1, 'I3', 'AVAILABLE'), "
        "(4, 4, 1, 'I4', 'AVAILABLE')"
    ))
    await session.execute(text(
        "INSERT INTO app.orders "
        "(id, client_id, pickup_point_id, start_date, end_date, "
        " total_price, deposit_paid, status, created_at) VALUES "
        "(1, 1, 1, '2026-01-01', '2026-01-02', 10, 100, 'COMPLETED', '2026-01-02'), "
        "(2, 2, 1, '2026-01-03', '2026-01-04', 10, 100, 'COMPLETED', '2026-01-04'), "
        "(3, 1, 1, '2026-01-05', '2026-01-06', 10, 100, 'COMPLETED', '2026-01-06'), "
        "(4, 1, 1, '2026-01-07', '2026-01-08', 10, 100, 'CANCELLED', '2026-01-08')"
    ))
    await session.execute(text(
        "INSERT INTO app.order_items (order_id, game_copy_id, price_at_rental) VALUES "
        "(1, 1, 10), (1, 2, 10), "
        "(2, 2, 10), (2, 3, 10), "
        "(3, 1, 10), (3, 4, 10), "
        "(4, 3, 10)"
    ))
    await session.commit()


@pytest.fixture
async def seeded(app_session):
    await _seed(app_session)
    return app_session


# ---------------------------------------------------------------------------
# get_cooccurrence
# ---------------------------------------------------------------------------


async def test_cooccurrence_of_game1(seeded, reader_session):
    result = await get_cooccurrence(reader_session, game_id=1)
    assert result == {2: 1, 4: 1}


async def test_cooccurrence_of_game2(seeded, reader_session):
    result = await get_cooccurrence(reader_session, game_id=2)
    assert result == {1: 1, 3: 1}


async def test_cooccurrence_ignores_cancelled(seeded, reader_session):
    """G3 appears in O2 (COMPLETED) and O4 (CANCELLED); O4 must not count."""
    result = await get_cooccurrence(reader_session, game_id=3)
    assert result == {2: 1}


async def test_cooccurrence_of_isolated_game(seeded, reader_session):
    result = await get_cooccurrence(reader_session, game_id=999)
    assert result == {}


# ---------------------------------------------------------------------------
# get_popularity
# ---------------------------------------------------------------------------


async def test_popularity_counts_completed_only(seeded, reader_session):
    result = await get_popularity(reader_session, [1, 2, 3, 4])
    # G1: O1, O3. G2: O1, O2. G3: O2. G4: O3. O4 is cancelled.
    assert result == {1: 2, 2: 2, 3: 1, 4: 1}


async def test_popularity_empty_ids(seeded, reader_session):
    assert await get_popularity(reader_session, []) == {}


async def test_popularity_unknown_ids(seeded, reader_session):
    assert await get_popularity(reader_session, [999]) == {}


# ---------------------------------------------------------------------------
# get_game_content
# ---------------------------------------------------------------------------


async def test_game_content_categories(seeded, reader_session):
    result = await get_game_content(reader_session, [1, 2, 3, 4])
    assert result[1].category_ids == frozenset({1, 2})
    assert result[2].category_ids == frozenset({2})
    assert result[3].category_ids == frozenset({3})
    assert result[4].category_ids == frozenset({1})


async def test_game_content_numeric_fields(seeded, reader_session):
    result = await get_game_content(reader_session, [1])
    game = result[1]
    assert game.min_players == 1
    assert game.max_players == 4
    assert game.playtime_minutes == 60


async def test_game_content_empty_ids(seeded, reader_session):
    assert await get_game_content(reader_session, []) == {}


# ---------------------------------------------------------------------------
# get_top_popular
# ---------------------------------------------------------------------------


async def test_top_popular_global(seeded, reader_session):
    result = await get_top_popular(
        reader_session, exclude_ids=[], category_ids=[], limit=10,
    )
    assert result == [1, 2, 3, 4]


async def test_top_popular_with_exclude(seeded, reader_session):
    result = await get_top_popular(
        reader_session, exclude_ids=[1, 2], category_ids=[], limit=10,
    )
    assert result == [3, 4]


async def test_top_popular_with_categories(seeded, reader_session):
    result = await get_top_popular(
        reader_session, exclude_ids=[], category_ids=[1], limit=10,
    )
    assert result == [1, 4]


async def test_top_popular_respects_limit(seeded, reader_session):
    result = await get_top_popular(
        reader_session, exclude_ids=[], category_ids=[], limit=2,
    )
    assert result == [1, 2]


# ---------------------------------------------------------------------------
# get_client_history
# ---------------------------------------------------------------------------


async def test_client_history_dedup_and_order(seeded, reader_session):
    """Alice's games: O1 (G1, G2), O3 (G1, G4). Ordered by most recent order."""
    result = await get_client_history(reader_session, client_id=1, limit=10)
    assert result == [4, 1, 2]


async def test_client_history_respects_limit(seeded, reader_session):
    result = await get_client_history(reader_session, client_id=1, limit=1)
    assert result == [4]


async def test_client_history_ignores_cancelled(seeded, reader_session):
    """O4 (G3) is cancelled and must not appear in Alice's history."""
    result = await get_client_history(reader_session, client_id=1, limit=10)
    assert 3 not in result


async def test_client_history_unknown_client(seeded, reader_session):
    assert await get_client_history(reader_session, client_id=999, limit=10) == []