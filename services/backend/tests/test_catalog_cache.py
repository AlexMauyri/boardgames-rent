"""Tests for app.services.catalog_cache."""

import pytest

from app.crud import board_game
from app.schemas import BoardGameRead, CategoryCreate, PickupPointCreate
from app.services import catalog_cache, create_category, create_pickup_point
from app.services.exceptions import NotFoundError
from tests.helpers import make_game, make_point


async def _keys(redis_client, pattern: str = "catalog:*") -> list[str]:
    return [k async for k in redis_client.scan_iter(match=pattern)]


async def test_second_read_comes_from_cache(session, redis_client):
    await create_category(session, CategoryCreate(name="Strategy"))
    first = await catalog_cache.list_categories(redis_client, session)

    # Written behind the cache's back: the cached answer must not change.
    await create_category(session, CategoryCreate(name="Coop"))
    second = await catalog_cache.list_categories(redis_client, session)

    assert [c.name for c in first] == ["Strategy"]
    assert second == first
    assert await _keys(redis_client) == ["catalog:categories:0:100"]


async def test_entry_has_ttl(session, redis_client):
    await catalog_cache.list_categories(redis_client, session)
    ttl = await redis_client.ttl("catalog:categories:0:100")
    assert ttl > 0


async def test_invalidate_categories_reloads(session, redis_client):
    await create_category(session, CategoryCreate(name="Strategy"))
    await catalog_cache.list_categories(redis_client, session)
    await create_category(session, CategoryCreate(name="Coop"))

    await catalog_cache.invalidate_catalog(redis_client, categories=True)
    rows = await catalog_cache.list_categories(redis_client, session)

    assert {c.name for c in rows} == {"Strategy", "Coop"}


async def test_game_filters_get_separate_entries(session, redis_client):
    await make_game(session, "Dune")
    await catalog_cache.list_games(redis_client, session)
    await catalog_cache.list_games(redis_client, session, players=2)
    await catalog_cache.list_games(redis_client, session, players=2)

    assert len(await _keys(redis_client, "catalog:games:list:*")) == 2


async def test_cover_url_survives_cache(session, redis_client):
    game_id = await make_game(session)
    row = await board_game.get(session, game_id)
    row.cover_key = "covers/1/abc.png"
    await session.commit()

    fresh = await catalog_cache.get_game_detail(redis_client, session, game_id)
    cached = await catalog_cache.get_game_detail(redis_client, session, game_id)
    listed = await catalog_cache.list_games(redis_client, session)
    listed_cached = await catalog_cache.list_games(redis_client, session)

    assert fresh.cover_url is not None
    assert cached.cover_url == fresh.cover_url
    assert listed_cached[0].cover_url == fresh.cover_url
    assert listed[0].cover_url == fresh.cover_url
    # Callers get the public schema, which never exposes the key.
    assert type(cached) is BoardGameRead
    assert "cover_key" not in cached.model_dump()


async def test_missing_game_is_not_cached(session, redis_client):
    with pytest.raises(NotFoundError):
        await catalog_cache.get_game_detail(redis_client, session, 999_999)
    assert await _keys(redis_client) == []


async def test_invalidate_flags_are_scoped(session, redis_client):
    await make_point(session)
    game_id = await make_game(session)
    await catalog_cache.list_categories(redis_client, session)
    await catalog_cache.list_pickup_points_public(redis_client, session)
    await catalog_cache.list_games(redis_client, session)
    await catalog_cache.get_game_detail(redis_client, session, game_id)

    await catalog_cache.invalidate_catalog(redis_client, points=True)
    assert await _keys(redis_client, "catalog:pickup_points:*") == []
    assert len(await _keys(redis_client, "catalog:games:*")) == 2

    await catalog_cache.invalidate_catalog(redis_client, games=True)
    assert await _keys(redis_client, "catalog:games:*") == []
    assert len(await _keys(redis_client, "catalog:categories:*")) == 1


async def test_invalidate_categories_drops_games(session, redis_client):
    await make_game(session)
    await catalog_cache.list_categories(redis_client, session)
    await catalog_cache.list_games(redis_client, session)

    await catalog_cache.invalidate_catalog(redis_client, categories=True)

    assert await _keys(redis_client) == []


async def test_invalidate_leaves_other_keys(session, redis_client):
    await redis_client.set("refresh:abc", "x")
    await create_pickup_point(session, PickupPointCreate(
        name="Center", address="a", phone="+7",
    ))
    await catalog_cache.list_pickup_points_public(redis_client, session)

    await catalog_cache.invalidate_catalog(
        redis_client, categories=True, games=True, points=True,
    )

    assert await _keys(redis_client) == []
    assert await redis_client.get("refresh:abc") == "x"
