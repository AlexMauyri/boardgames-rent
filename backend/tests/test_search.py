"""Tests for catalog browsing and availability search."""

import pytest

from app.schemas import BoardGameCreate, CategoryCreate
from app.services import (
    NotFoundError,
    add_new_game_to_catalog,
    cancel_order,
    create_category,
    create_order,
    deactivate_pickup_point,
    list_games,
    search_available_games,
)
from decimal import Decimal

from tests.helpers import (
    make_client,
    make_copy,
    make_game,
    make_point,
    order_request,
)


async def _game(session, title, low, high, minutes, category_ids=()):
    row = await add_new_game_to_catalog(session, BoardGameCreate(
        title=title, min_players=low, max_players=high,
        playtime_minutes=minutes, daily_price=Decimal("100"),
        deposit_price=Decimal("500"), category_ids=list(category_ids),
    ))
    return row.id


def _ids(rows):
    return [r.id for r in rows]


async def test_list_games_filters_by_players_time_and_category(session):
    party = (await create_category(session, CategoryCreate(name="Party"))).id
    quick = await _game(session, "Quick", 2, 5, 30, [party])
    long_ = await _game(session, "Long", 2, 4, 180)
    big = await _game(session, "Big", 6, 12, 40, [party])

    assert _ids(await list_games(session)) == [quick, long_, big]
    assert _ids(await list_games(session, players=4)) == [quick, long_]
    assert _ids(await list_games(session, playtime_max=60)) == [quick, big]
    assert _ids(await list_games(session, category_id=party)) == [quick, big]
    assert _ids(await list_games(
        session, players=4, playtime_max=60, category_id=party,
    )) == [quick]


async def test_search_reports_stock_at_point_and_elsewhere(session):
    here = await make_point(session, "Center")
    north = await make_point(session, "North")
    game = await make_game(session)
    await make_copy(session, game, here, "INV-1")
    await make_copy(session, game, north, "INV-2")
    await make_copy(session, game, north, "INV-3")

    [item] = await search_available_games(session, here)

    assert item.game.id == game
    assert item.free_at_point == 1
    assert item.free_elsewhere == 2


async def test_search_puts_games_ready_at_the_point_first(session):
    here = await make_point(session, "Center")
    north = await make_point(session, "North")
    far = await make_game(session, "Far")
    near = await make_game(session, "Near")
    await make_copy(session, far, north, "INV-1")
    await make_copy(session, near, here, "INV-2")

    items = await search_available_games(session, here)

    assert [i.game.id for i in items] == [near, far]


async def test_search_applies_meeting_filters(session):
    here = await make_point(session, "Center")
    fits = await _game(session, "Fits", 3, 5, 60)
    too_big = await _game(session, "TooBig", 6, 8, 60)
    too_long = await _game(session, "TooLong", 3, 5, 200)
    for n, g in enumerate((fits, too_big, too_long)):
        await make_copy(session, g, here, f"INV-{n}")

    items = await search_available_games(
        session, here, players=4, playtime_max=90,
    )

    assert [i.game.id for i in items] == [fits]


async def test_search_skips_games_without_free_boxes(session):
    here = await make_point(session, "Center")
    stocked = await make_game(session, "Stocked")
    empty = await make_game(session, "Empty")
    damaged = await make_game(session, "Damaged")
    await make_copy(session, stocked, here, "INV-1")
    await make_copy(session, damaged, here, "INV-2", status="DAMAGED")

    items = await search_available_games(session, here)

    assert [i.game.id for i in items] == [stocked]
    assert empty not in [i.game.id for i in items]


async def test_search_ignores_boxes_held_by_open_orders(session):
    here = await make_point(session, "Center")
    client_id = await make_client(session)
    game = await make_game(session)
    await make_copy(session, game, here, "INV-1")
    order = await create_order(session, client_id, order_request(here, [game]))

    assert await search_available_games(session, here) == []

    await cancel_order(session, order.id, client_id)
    assert len(await search_available_games(session, here)) == 1


async def test_search_unknown_point_not_found(session):
    with pytest.raises(NotFoundError):
        await search_available_games(session, 999999)


async def test_search_inactive_point_rejected(session):
    here = await make_point(session, "Center")
    await deactivate_pickup_point(session, here)

    with pytest.raises(ValueError):
        await search_available_games(session, here)


async def test_search_paging(session):
    here = await make_point(session, "Center")
    ids = []
    for n in range(3):
        game = await make_game(session, f"G{n}")
        await make_copy(session, game, here, f"INV-{n}")
        ids.append(game)

    page = await search_available_games(session, here, skip=1, limit=1)

    assert [i.game.id for i in page] == [ids[1]]
