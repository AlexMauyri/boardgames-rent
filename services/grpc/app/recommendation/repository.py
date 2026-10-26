"""Read-only queries for the recommendation engine."""

from collections.abc import Sequence

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.recommendation.types import GameContent

_COMPLETED = "COMPLETED"


async def get_cooccurrence(
    session: AsyncSession,
    game_id: int,
) -> dict[int, int]:
    """Count distinct completed orders in which ``game_id`` appears with each other game.

    A candidate game ``b`` co-occurs with the target ``a`` once per order
    that contains both. Cancelled, in-transit or otherwise unfinished
    orders do not contribute: recommendations learn from rentals that
    actually happened.

    Args:
        session: Async session (read-only).
        game_id: Target catalog game id.

    Returns:
        Mapping ``{other_game_id: distinct_order_count}``. Games that
        never co-occur with ``game_id`` are absent from the result.
    """
    stmt = text(
        """
        SELECT gc_b.game_id AS other_game_id,
               COUNT(DISTINCT oi_a.order_id) AS cooc
        FROM app.order_items oi_a
        JOIN app.game_copies gc_a ON gc_a.id = oi_a.game_copy_id
        JOIN app.order_items oi_b ON oi_b.order_id = oi_a.order_id
        JOIN app.game_copies gc_b ON gc_b.id = oi_b.game_copy_id
        JOIN app.orders o ON o.id = oi_a.order_id
        WHERE gc_a.game_id = :game_id
          AND gc_b.game_id <> gc_a.game_id
          AND o.status = :completed
        GROUP BY gc_b.game_id
        """
    )
    result = await session.execute(
        stmt, {"game_id": game_id, "completed": _COMPLETED},
    )
    return {row.other_game_id: row.cooc for row in result}


async def get_popularity(
    session: AsyncSession,
    game_ids: Sequence[int],
) -> dict[int, int]:
    """Count distinct completed orders per game.

    Args:
        session: Async session (read-only).
        game_ids: Games to count. If empty, returns an empty mapping.

    Returns:
        Mapping ``{game_id: distinct_order_count}``. Games never rented
        are absent from the result.
    """
    if not game_ids:
        return {}

    stmt = text(
        """
        SELECT gc.game_id,
               COUNT(DISTINCT oi.order_id) AS pop
        FROM app.order_items oi
        JOIN app.game_copies gc ON gc.id = oi.game_copy_id
        JOIN app.orders o ON o.id = oi.order_id
        WHERE o.status = :completed
          AND gc.game_id IN :game_ids
        GROUP BY gc.game_id
        """
    ).bindparams(bindparam("game_ids", expanding=True))
    result = await session.execute(
        stmt, {"game_ids": list(game_ids), "completed": _COMPLETED},
    )
    return {row.game_id: row.pop for row in result}


async def get_game_content(
    session: AsyncSession,
    game_ids: Sequence[int],
) -> dict[int, GameContent]:
    """Fetch categorical and numeric features for a set of games.

    Args:
        session: Async session (read-only).
        game_ids: Games to fetch. If empty, returns an empty mapping.

    Returns:
        Mapping ``{game_id: GameContent}``. Games that do not exist are
        absent.
    """
    if not game_ids:
        return {}

    stmt = text(
        """
        SELECT bg.id AS game_id,
               bg.min_players,
               bg.max_players,
               bg.playtime_minutes,
               COALESCE(
                   array_agg(gc.category_id)
                       FILTER (WHERE gc.category_id IS NOT NULL),
                   ARRAY[]::integer[]
               ) AS category_ids
        FROM app.board_games bg
        LEFT JOIN app.game_categories gc ON gc.game_id = bg.id
        WHERE bg.id IN :game_ids
        GROUP BY bg.id, bg.min_players, bg.max_players, bg.playtime_minutes
        """
    ).bindparams(bindparam("game_ids", expanding=True))
    result = await session.execute(stmt, {"game_ids": list(game_ids)})

    contents: dict[int, GameContent] = {}
    for row in result:
        contents[row.game_id] = GameContent(
            game_id=row.game_id,
            category_ids=frozenset(row.category_ids),
            min_players=row.min_players,
            max_players=row.max_players,
            playtime_minutes=row.playtime_minutes,
        )
    return contents


async def get_top_popular(
    session: AsyncSession,
    *,
    exclude_ids: Sequence[int],
    category_ids: Sequence[int],
    limit: int,
) -> list[int]:
    """Rank games by completed rentals, optionally restricted to categories.

    Used by both fallback paths: global popularity (no history) and
    popularity within the client's historical categories.

    Args:
        session: Async session (read-only).
        exclude_ids: Games that must not appear in the result.
        category_ids: If non-empty, restrict to games in at least one of
            these categories.
        limit: Maximum number of ids to return.

    Returns:
        Game ids in ``COUNT(DISTINCT order_id) DESC, game_id ASC`` order.
        Fewer than ``limit`` ids if not enough games match.
    """
    params: dict = {"limit": limit, "completed": _COMPLETED}
    where_parts = ["o.status = :completed"]
    binds = []

    if exclude_ids:
        where_parts.append("gc.game_id NOT IN :exclude_ids")
        params["exclude_ids"] = list(exclude_ids)
        binds.append(bindparam("exclude_ids", expanding=True))

    if category_ids:
        where_parts.append(
            "gc.game_id IN ("
            "  SELECT game_id FROM app.game_categories"
            "  WHERE category_id IN :category_ids"
            ")"
        )
        params["category_ids"] = list(category_ids)
        binds.append(bindparam("category_ids", expanding=True))

    where_sql = " AND ".join(where_parts)

    stmt = text(
        f"""
        SELECT gc.game_id
        FROM app.order_items oi
        JOIN app.game_copies gc ON gc.id = oi.game_copy_id
        JOIN app.orders o ON o.id = oi.order_id
        WHERE {where_sql}
        GROUP BY gc.game_id
        ORDER BY COUNT(DISTINCT oi.order_id) DESC, gc.game_id ASC
        LIMIT :limit
        """
    )
    if binds:
        stmt = stmt.bindparams(*binds)

    result = await session.execute(stmt, params)
    return [row.game_id for row in result]


async def get_client_history(
    session: AsyncSession,
    client_id: int,
    limit: int,
) -> list[int]:
    """Return distinct games from a client's completed orders, most recent first.

    A game rented twice appears once; its position reflects the most
    recent completed rental. Cancelled and unfinished orders do not
    contribute, so recommendations never learn from a booking that did
    not become a rental.

    Args:
        session: Async session (read-only).
        client_id: Client primary key.
        limit: Maximum number of distinct games.

    Returns:
        Game ids ordered by ``MAX(orders.created_at) DESC``; at most
        ``limit`` ids.
    """
    stmt = text(
        """
        SELECT gc.game_id
        FROM app.order_items oi
        JOIN app.game_copies gc ON gc.id = oi.game_copy_id
        JOIN app.orders o ON o.id = oi.order_id
        WHERE o.client_id = :client_id
          AND o.status = :completed
        GROUP BY gc.game_id
        ORDER BY MAX(o.created_at) DESC, gc.game_id DESC
        LIMIT :limit
        """
    )
    result = await session.execute(
        stmt,
        {
            "client_id": client_id,
            "completed": _COMPLETED,
            "limit": limit,
        },
    )
    return [row.game_id for row in result]