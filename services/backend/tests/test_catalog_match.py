"""Tests for ranking games for a meeting, with an injected ranker."""

from decimal import Decimal

import pytest

from app.schemas import BoardGameCreate, CategoryCreate
from app.services import (
    NotFoundError,
    ServiceUnavailableError,
    ServiceValueError,
    add_new_game_to_catalog,
    create_category,
    deactivate_pickup_point,
    match_games,
)
from app.services.catalog import RankedGame
from tests.helpers import make_copy, make_point


class _StubRanker:
    """Records the request and returns a prepared ranking."""

    def __init__(self, ranked: list[RankedGame]) -> None:
        self.ranked = ranked
        self.calls: list[dict] = []

    async def rank_games(self, players, max_playtime_minutes,
                         preferred_category_ids, candidates, limit):
        self.calls.append({
            "players": players,
            "minutes": max_playtime_minutes,
            "categories": list(preferred_category_ids),
            "candidates": list(candidates),
            "limit": limit,
        })
        return self.ranked


class _BrokenRanker:
    async def rank_games(self, *args):
        raise ServiceUnavailableError("Matching service unavailable")


async def _game(session, title, low, high, minutes, category_ids=()):
    row = await add_new_game_to_catalog(session, BoardGameCreate(
        title=title, min_players=low, max_players=high,
        playtime_minutes=minutes, daily_price=Decimal("100"),
        deposit_price=Decimal("500"), category_ids=list(category_ids),
    ))
    return row.id


async def test_candidates_carry_stock_and_categories_and_skip_unavailable(session):
    here = await make_point(session, "Here")
    there = await make_point(session, "There")
    party = (await create_category(session, CategoryCreate(name="Party"))).id
    on_shelf = await _game(session, "OnShelf", 2, 6, 60, [party])
    far = await _game(session, "Far", 2, 6, 60)
    await _game(session, "NoBoxes", 2, 6, 60)
    await make_copy(session, on_shelf, here, "I1")
    await make_copy(session, far, there, "I2")
    await make_copy(session, far, there, "I3")
    ranker = _StubRanker([])

    await match_games(session, ranker, here, 4, 90, [party], limit=5)

    call = ranker.calls[0]
    assert (call["players"], call["minutes"], call["limit"]) == (4, 90, 5)
    assert call["categories"] == [party]
    by_id = {c.game_id: c for c in call["candidates"]}
    assert set(by_id) == {on_shelf, far}
    assert (by_id[on_shelf].free_at_point, by_id[on_shelf].free_elsewhere) == (1, 0)
    assert (by_id[far].free_at_point, by_id[far].free_elsewhere) == (0, 2)
    assert list(by_id[on_shelf].category_ids) == [party]


async def test_result_follows_the_ranking_and_carries_stock(session):
    here = await make_point(session)
    first = await _game(session, "First", 2, 6, 60)
    second = await _game(session, "Second", 2, 6, 60)
    await make_copy(session, first, here, "I1")
    await make_copy(session, second, here, "I2")
    ranker = _StubRanker([
        RankedGame(second, 0.9, "fits_meeting"),
        RankedGame(first, 0.4, "needs_delivery"),
    ])

    items = await match_games(session, ranker, here, 4, 90)

    assert [i.game.id for i in items] == [second, first]
    assert items[0].score == 0.9
    assert items[0].reason == "fits_meeting"
    assert items[0].free_at_point == 1


async def test_unavailable_service_falls_back_to_a_plain_filter(session):
    here = await make_point(session, "Here")
    there = await make_point(session, "There")
    delivered = await _game(session, "Delivered", 2, 6, 60)
    at_hand = await _game(session, "AtHand", 2, 6, 60)
    wrong_size = await _game(session, "Big", 8, 12, 60)
    too_long = await _game(session, "Long", 2, 6, 240)
    for i, game in enumerate((delivered, at_hand, wrong_size, too_long)):
        await make_copy(session, game, there if game == delivered else here, f"I{i}")

    items = await match_games(session, _BrokenRanker(), here, 4, 90)

    assert [i.game.id for i in items] == [at_hand, delivered]
    assert {i.reason for i in items} == {"fallback_filter"}
    assert {i.score for i in items} == {0.0}


async def test_without_a_ranker_the_filter_is_used_too(session):
    here = await make_point(session)
    game = await _game(session, "Only", 2, 6, 60)
    await make_copy(session, game, here, "I1")

    items = await match_games(session, None, here, 4, 90)

    assert [i.game.id for i in items] == [game]


async def test_fallback_honours_preferred_categories_and_limit(session):
    here = await make_point(session)
    party = (await create_category(session, CategoryCreate(name="Party"))).id
    tagged = [await _game(session, f"T{i}", 2, 6, 60, [party]) for i in range(3)]
    plain = await _game(session, "Plain", 2, 6, 60)
    for i, game in enumerate([*tagged, plain]):
        await make_copy(session, game, here, f"I{i}")

    items = await match_games(session, None, here, 4, 90, [party], limit=2)

    assert [i.game.id for i in items] == tagged[:2]


async def test_unknown_pickup_point(session):
    with pytest.raises(NotFoundError):
        await match_games(session, None, 999999, 4, 90)


async def test_inactive_pickup_point(session):
    here = await make_point(session)
    await deactivate_pickup_point(session, here)

    with pytest.raises(ServiceValueError):
        await match_games(session, None, here, 4, 90)
