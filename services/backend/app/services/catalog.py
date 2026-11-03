"""Public, read-only catalog services."""

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import board_game, category, game_copy, pickup_point
from app.schemas import (
    BoardGameRead,
    CategoryRead,
    GameSearchItem,
    MatchedGameItem,
    PickupPointRead,
)
from app.services.exceptions import (
    NotFoundError,
    ServiceUnavailableError,
    ServiceValueError,
)

logger = logging.getLogger(__name__)

FALLBACK_REASON = "fallback_filter"


@dataclass(frozen=True)
class MatchCandidate:
    """A game offered to the matching service, with its stock figures."""

    game_id: int
    min_players: int
    max_players: int
    playtime_minutes: int
    category_ids: Sequence[int]
    free_at_point: int
    free_elsewhere: int


@dataclass(frozen=True)
class RankedGame:
    """A game as ranked by the matching service."""

    game_id: int
    score: float
    reason: str


class GameRanker(Protocol):
    """Anything that can rank games for a meeting, e.g. the gRPC client."""

    async def rank_games(
        self,
        players: int,
        max_playtime_minutes: int,
        preferred_category_ids: Sequence[int],
        candidates: Sequence[MatchCandidate],
        limit: int,
    ) -> list[RankedGame]:
        """Rank ``candidates`` for the meeting, best first."""


async def list_categories(
    session: AsyncSession,
    skip: int = 0,
    limit: int = 100,
) -> list[CategoryRead]:
    """List all categories, id-ascending.

    Args:
        session: Active async session.
        skip: Rows to skip.
        limit: Maximum rows to return.

    Returns:
        Matching rows; empty list if none.
    """
    rows = await category.list(session, skip=skip, limit=limit)
    return [CategoryRead.model_validate(row) for row in rows]


async def list_pickup_points_public(
    session: AsyncSession,
    skip: int = 0,
    limit: int = 100,
) -> list[PickupPointRead]:
    """List active pickup points, id-ascending.

    Args:
        session: Active async session.
        skip: Rows to skip.
        limit: Maximum rows to return.

    Returns:
        Active rows; empty list if none.
    """
    rows = await pickup_point.list_active(session, skip=skip, limit=limit)
    return [PickupPointRead.model_validate(row) for row in rows]


async def get_game_detail(
    session: AsyncSession,
    game_id: int,
) -> BoardGameRead:
    """Fetch a single board game by id.

    Args:
        session: Active async session.
        game_id: Primary key of the board game.

    Returns:
        The board game.

    Raises:
        NotFoundError: No board game with that id.
    """
    obj = await board_game.get_with_categories(session, game_id)
    if obj is None:
        raise NotFoundError("BoardGame", game_id)
    return BoardGameRead.model_validate(obj)

async def list_games(
    session: AsyncSession,
    players: int | None = None,
    playtime_max: int | None = None,
    category_id: int | None = None,
    skip: int = 0,
    limit: int = 100,
) -> list[BoardGameRead]:
    """Browse the catalog, optionally filtered.

    Args:
        session: Active async session.
        players: Keep games whose supported player range includes this count.
            None disables the filter.
        playtime_max: Keep games whose average play time is at most this many
            minutes. None disables the filter.
        category_id: Keep games in this category. None disables the filter.
        skip: Rows to skip.
        limit: Maximum rows to return.

    Returns:
        Matching games, id-ascending; empty list if none.
    """
    rows = await board_game.list_filtered(
        session,
        players=players,
        playtime_max=playtime_max,
        category_id=category_id,
        skip=skip,
        limit=limit,
    )
    return [BoardGameRead.model_validate(row) for row in rows]


async def search_available_games(
    session: AsyncSession,
    pickup_point_id: int,
    players: int | None = None,
    playtime_max: int | None = None,
    category_id: int | None = None,
    skip: int = 0,
    limit: int = 100,
) -> list[GameSearchItem]:
    """Find games that fit the meeting and can reach the chosen point.

    Only games with at least one free box anywhere are returned. Games that
    can be collected at once come first; the rest need a delivery.

    Args:
        session: Active async session.
        pickup_point_id: Point where the client would collect the game.
        players: Number of players. None disables the filter.
        playtime_max: Maximum play time in minutes. None disables the filter.
        category_id: Required category. None disables the filter.
        skip: Results to skip.
        limit: Maximum results to return.

    Returns:
        Matching games with their stock; empty list if none.

    Raises:
        NotFoundError: No such pickup point.
        ServiceValueError: The pickup point is not active.
    """
    point = await pickup_point.get(session, pickup_point_id)
    if point is None:
        raise NotFoundError("PickupPoint", pickup_point_id)
    if not point.is_active:
        raise ServiceValueError("Pickup point is not active")

    games = await board_game.list_filtered(
        session,
        players=players,
        playtime_max=playtime_max,
        category_id=category_id,
        limit=10_000,
    )
    free = await game_copy.count_free(session, [g.id for g in games])

    items: list[GameSearchItem] = []
    for game in games:
        at_point = free.get((game.id, pickup_point_id), 0)
        total = sum(n for (g, _), n in free.items() if g == game.id)
        if total == 0:
            continue
        items.append(GameSearchItem(
            game=BoardGameRead.model_validate(game),
            free_at_point=at_point,
            free_elsewhere=total - at_point,
        ))
    items.sort(key=lambda item: (item.free_at_point == 0, item.game.id))
    return items[skip:skip + limit]


async def match_games(
    session: AsyncSession,
    ranker: GameRanker | None,
    pickup_point_id: int,
    players: int,
    playtime_max: int,
    category_ids: Sequence[int] = (),
    limit: int = 10,
) -> list[MatchedGameItem]:
    """Rank the games that suit a meeting and can reach the chosen point.

    Every game with a free box anywhere is offered to the matching service,
    which scores it against the meeting. When the service is not configured
    or does not answer, a plain filter takes over (right player count, short
    enough, in a preferred category), collectable games first, with score 0.

    Args:
        session: Active async session.
        ranker: The matching service client, or None.
        pickup_point_id: Point where the client would collect the game.
        players: Number of players, at least 1.
        playtime_max: Time the group has, in minutes.
        category_ids: Favourite categories; empty means no preference.
        limit: Maximum results to return.

    Returns:
        Matching games, best first; empty list if none.

    Raises:
        NotFoundError: No such pickup point.
        ServiceValueError: The pickup point is not active.
    """
    point = await pickup_point.get(session, pickup_point_id)
    if point is None:
        raise NotFoundError("PickupPoint", pickup_point_id)
    if not point.is_active:
        raise ServiceValueError("Pickup point is not active")

    games = await board_game.list_with_categories(session)
    free = await game_copy.count_free(session, [g.id for g in games])

    candidates: list[MatchCandidate] = []
    by_id = {}
    for game in games:
        at_point = free.get((game.id, pickup_point_id), 0)
        total = sum(n for (g, _), n in free.items() if g == game.id)
        if total == 0:
            continue
        by_id[game.id] = game
        candidates.append(MatchCandidate(
            game_id=game.id,
            min_players=game.min_players,
            max_players=game.max_players,
            playtime_minutes=game.playtime_minutes,
            category_ids=sorted(c.id for c in game.categories),
            free_at_point=at_point,
            free_elsewhere=total - at_point,
        ))

    ranked: list[RankedGame] | None = None
    if ranker is not None:
        try:
            ranked = await ranker.rank_games(
                players, playtime_max, list(category_ids), candidates, limit,
            )
        except ServiceUnavailableError:
            logger.warning("matching service unavailable, using plain filter")
    if ranked is None:
        ranked = _filter_fallback(
            candidates, players, playtime_max, set(category_ids), limit,
        )

    stock = {c.game_id: c for c in candidates}
    return [
        MatchedGameItem(
            game=BoardGameRead.model_validate(by_id[r.game_id]),
            score=r.score,
            reason=r.reason,
            free_at_point=stock[r.game_id].free_at_point,
            free_elsewhere=stock[r.game_id].free_elsewhere,
        )
        for r in ranked
        if r.game_id in by_id
    ]


def _filter_fallback(
    candidates: Sequence[MatchCandidate],
    players: int,
    playtime_max: int,
    category_ids: set[int],
    limit: int,
) -> list[RankedGame]:
    """Plain-filter ranking used when the matching service is unavailable."""
    fitting = [
        c for c in candidates
        if c.min_players <= players <= c.max_players
        and c.playtime_minutes <= playtime_max
        and (not category_ids or category_ids & set(c.category_ids))
    ]
    fitting.sort(key=lambda c: (c.free_at_point == 0, c.game_id))
    return [
        RankedGame(game_id=c.game_id, score=0.0, reason=FALLBACK_REASON)
        for c in fitting[:limit]
    ]
