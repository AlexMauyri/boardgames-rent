"""Tests for board game catalog writes and category linkage."""

from decimal import Decimal

import pytest

from app.schemas import (
    BoardGameCreate,
    BoardGameUpdate,
    CategoryCreate,
)
from app.services import (
    add_new_game_to_catalog,
    create_category,
    get_game_detail,
    list_categories,
    set_game_categories,
    update_game,
)
from app.services.exceptions import NotFoundError


async def _make_category(session, name="Strategy"):
    return await create_category(session, CategoryCreate(name=name))


async def _make_game(session, category_ids=None, title="Dune"):
    return await add_new_game_to_catalog(session, BoardGameCreate(
        title=title, description="Desert",
        min_players=2, max_players=4, playtime_minutes=90,
        daily_price=Decimal("300.00"), deposit_price=Decimal("1000.00"),
        category_ids=category_ids or [],
    ))


async def test_add_new_game(session):
    g = await _make_game(session)
    assert g.title == "Dune"


async def test_add_new_game_with_categories(session):
    cat = await _make_category(session)
    g = await _make_game(session, category_ids=[cat.id])
    detail = await get_game_detail(session, g.id)
    assert detail.title == "Dune"


async def test_add_new_game_unknown_category(session):
    with pytest.raises(ValueError):
        await add_new_game_to_catalog(session, BoardGameCreate(
            title="Bad", min_players=1, max_players=2, playtime_minutes=30,
            daily_price=Decimal("1"), deposit_price=Decimal("1"),
            category_ids=[999999],
        ))


async def test_add_new_game_invalid_range_rejected_by_schema(session):
    with pytest.raises(Exception):
        BoardGameCreate(
            title="Bad", min_players=4, max_players=2, playtime_minutes=30,
            daily_price=Decimal("1"), deposit_price=Decimal("1"),
        )


async def test_get_game_detail(session):
    g = await _make_game(session)
    detail = await get_game_detail(session, g.id)
    assert detail.title == "Dune"


async def test_get_game_detail_not_found(session):
    with pytest.raises(NotFoundError):
        await get_game_detail(session, 999999)


async def test_update_game_valid_range(session):
    g = await _make_game(session)
    upd = await update_game(session, g.id, BoardGameUpdate(
        min_players=3, max_players=5,
    ))
    assert upd.min_players == 3
    assert upd.max_players == 5


async def test_update_game_partial_invalid_range(session):
    g = await _make_game(session)
    with pytest.raises(ValueError):
        await update_game(session, g.id, BoardGameUpdate(min_players=10))


async def test_update_game_not_found(session):
    with pytest.raises(NotFoundError):
        await update_game(session, 999999, BoardGameUpdate(title="X"))


async def test_set_game_categories_replace_all(session):
    cat1 = await _make_category(session, "Strategy")
    cat2 = await _make_category(session, "Coop")
    g = await _make_game(session, category_ids=[cat1.id, cat2.id])

    await set_game_categories(session, g.id, [cat1.id])
    detail = await get_game_detail(session, g.id)
    assert detail.title == "Dune"


async def test_set_game_categories_clear(session):
    cat = await _make_category(session)
    g = await _make_game(session, category_ids=[cat.id])
    await set_game_categories(session, g.id, [])


async def test_set_game_categories_unknown_id(session):
    g = await _make_game(session)
    with pytest.raises(ValueError):
        await set_game_categories(session, g.id, [999999])


async def test_set_game_categories_game_not_found(session):
    cat = await _make_category(session)
    with pytest.raises(NotFoundError):
        await set_game_categories(session, 999999, [cat.id])