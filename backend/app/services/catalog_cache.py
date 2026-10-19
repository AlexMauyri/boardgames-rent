"""Redis read-through cache over the public catalog services.

Only reference data that changes through the admin API is cached:
categories, active pickup points, the game list and game cards. Stock
search (`catalog.search_available_games`) is deliberately left out — free
box counts change with every order, delivery and return, so a cached
answer would go stale long before any TTL ran out.

Admin write paths call `invalidate_catalog` after the change is committed.
"""

import hashlib
import json
import logging
from collections.abc import Awaitable, Callable

import redis.asyncio as redis
from pydantic import TypeAdapter
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.schemas import BoardGameRead, CategoryRead, PickupPointRead
from app.services import catalog

logger = logging.getLogger(__name__)

_PREFIX = "catalog"
_CATEGORIES = f"{_PREFIX}:categories"
_POINTS = f"{_PREFIX}:pickup_points"
_GAMES = f"{_PREFIX}:games"

_SCAN_COUNT = 500


class _CachedGame(BoardGameRead):
    """`BoardGameRead` that keeps `cover_key` in its JSON.

    The public schema excludes `cover_key` from serialisation and derives
    `cover_url` from it, so a plain round trip through Redis would lose the
    cover. This subclass is only the cache's storage format.
    """

    cover_key: str | None = None


def _to_cached(game: BoardGameRead) -> _CachedGame:
    return _CachedGame.model_validate(game, from_attributes=True)


def _to_public(game: _CachedGame) -> BoardGameRead:
    return BoardGameRead.model_validate(game.model_dump())


_categories_adapter = TypeAdapter(list[CategoryRead])
_points_adapter = TypeAdapter(list[PickupPointRead])
_games_adapter = TypeAdapter(list[_CachedGame])
_game_adapter = TypeAdapter(_CachedGame)


def _digest(params: dict[str, object]) -> str:
    """Stable short hash of a filter set, used as a key suffix."""
    raw = json.dumps(params, sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(raw.encode()).hexdigest()


async def _cached[T](
    redis_client: redis.Redis,
    key: str,
    adapter: TypeAdapter[T],
    load: Callable[[], Awaitable[T]],
) -> T:
    """Return the value under `key`, loading and storing it on a miss."""
    hit = await redis_client.get(key)
    if hit is not None:
        return adapter.validate_json(hit)

    logger.debug("cache miss key=%s", key)

    value = await load()
    await redis_client.set(
        key, adapter.dump_json(value), ex=settings.catalog_cache_ttl,
    )
    return value


async def list_categories(
    redis_client: redis.Redis,
    session: AsyncSession,
    skip: int = 0,
    limit: int = 100,
) -> list[CategoryRead]:
    """Cached `catalog.list_categories`."""
    return await _cached(
        redis_client,
        f"{_CATEGORIES}:{skip}:{limit}",
        _categories_adapter,
        lambda: catalog.list_categories(session, skip=skip, limit=limit),
    )


async def list_pickup_points_public(
    redis_client: redis.Redis,
    session: AsyncSession,
    skip: int = 0,
    limit: int = 100,
) -> list[PickupPointRead]:
    """Cached `catalog.list_pickup_points_public`."""
    return await _cached(
        redis_client,
        f"{_POINTS}:{skip}:{limit}",
        _points_adapter,
        lambda: catalog.list_pickup_points_public(
            session, skip=skip, limit=limit,
        ),
    )


async def _load_games(
    session: AsyncSession, params: dict[str, int | None],
) -> list[_CachedGame]:
    return [_to_cached(g) for g in await catalog.list_games(session, **params)]


async def _load_game(session: AsyncSession, game_id: int) -> _CachedGame:
    return _to_cached(await catalog.get_game_detail(session, game_id))


async def list_games(
    redis_client: redis.Redis,
    session: AsyncSession,
    players: int | None = None,
    playtime_max: int | None = None,
    category_id: int | None = None,
    skip: int = 0,
    limit: int = 100,
) -> list[BoardGameRead]:
    """Cached `catalog.list_games`; one entry per distinct filter set."""
    params = {
        "players": players,
        "playtime_max": playtime_max,
        "category_id": category_id,
        "skip": skip,
        "limit": limit,
    }
    games = await _cached(
        redis_client,
        f"{_GAMES}:list:{_digest(params)}",
        _games_adapter,
        lambda: _load_games(session, params),
    )
    return [_to_public(g) for g in games]


async def get_game_detail(
    redis_client: redis.Redis,
    session: AsyncSession,
    game_id: int,
) -> BoardGameRead:
    """Cached `catalog.get_game_detail`.

    Raises:
        NotFoundError: No board game with that id. Misses are not cached.
    """
    game = await _cached(
        redis_client,
        f"{_GAMES}:detail:{game_id}",
        _game_adapter,
        lambda: _load_game(session, game_id),
    )
    return _to_public(game)


async def _drop_prefix(redis_client: redis.Redis, prefix: str) -> None:
    """Remove every key under `prefix:` without blocking Redis (no KEYS)."""
    batch: list[str] = []
    async for key in redis_client.scan_iter(
        match=f"{prefix}:*", count=_SCAN_COUNT,
    ):
        batch.append(key)
        if len(batch) >= _SCAN_COUNT:
            await redis_client.unlink(*batch)
            batch.clear()
    if batch:
        await redis_client.unlink(*batch)


async def invalidate_catalog(
    redis_client: redis.Redis,
    *,
    categories: bool = False,
    games: bool = False,
    points: bool = False,
) -> None:
    """Drop cached catalog entries after an admin change.

    Args:
        redis_client: Shared Redis client.
        categories: Category list changed. Implies `games`, because game
            lists filtered by `category_id` depend on category membership.
        games: A game, its categories or its cover changed.
        points: A pickup point was created, edited or (de)activated.
    """
    if categories:
        await _drop_prefix(redis_client, _CATEGORIES)
        games = True
    if games:
        await _drop_prefix(redis_client, _GAMES)
    if points:
        await _drop_prefix(redis_client, _POINTS)

    if categories or games or points:
        logger.info(
            "catalog cache invalidated categories=%s games=%s points=%s",
            categories, games, points,
        )