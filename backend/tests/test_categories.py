"""Tests for create_category, update_category, delete_category."""

import pytest

from app.schemas import CategoryCreate, CategoryUpdate
from app.services import create_category, delete_category, update_category
from app.services.exceptions import ConflictError, NotFoundError


async def _make_category(session, name="Strategy"):
    return await create_category(session, CategoryCreate(name=name))


async def test_create_category(session):
    cat = await _make_category(session)
    assert cat.name == "Strategy"


async def test_create_category_duplicate(session):
    await _make_category(session)
    with pytest.raises(ConflictError):
        await _make_category(session)


async def test_update_category_rename(session):
    cat = await _make_category(session)
    updated = await update_category(
        session, cat.id, CategoryUpdate(name="StrategyGames"),
    )
    assert updated.name == "StrategyGames"


async def test_update_category_same_name_is_not_a_conflict(session):
    cat = await _make_category(session)
    same = await update_category(
        session, cat.id, CategoryUpdate(name="Strategy"),
    )
    assert same.name == "Strategy"


async def test_update_category_rename_to_existing(session):
    cat1 = await _make_category(session, "Strategy")
    await _make_category(session, "Coop")
    with pytest.raises(ConflictError):
        await update_category(session, cat1.id, CategoryUpdate(name="Coop"))


async def test_update_category_not_found(session):
    with pytest.raises(NotFoundError):
        await update_category(session, 999999, CategoryUpdate(name="X"))


async def test_delete_category(session):
    cat = await _make_category(session, "Temp")
    await delete_category(session, cat.id)


async def test_delete_category_not_found(session):
    with pytest.raises(NotFoundError):
        await delete_category(session, 999999)