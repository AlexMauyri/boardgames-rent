"""Choosing which physical boxes serve an order.

A pure function with no database access, so the rules can be tested without
a database.

Rules:
    * Boxes already at the pickup point are preferred.
    * Every box that must travel comes from one single source point, because
      an order has at most one delivery and a delivery has one departure
      point.
    * Among several possible source points the one with the lowest id wins,
      which keeps the choice deterministic.
"""

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from app.services.exceptions import NotAvailableError


class _CopyLike(Protocol):
    """Structural type for the values `plan_fulfilment` reads."""

    id: int
    game_id: int
    current_point_id: int | None


@dataclass(frozen=True)
class FulfilmentPlan:
    """The boxes chosen for an order.

    Attributes:
        copies: The chosen boxes, one per requested unit.
        source_point_id: Point the travelling boxes depart from, or None when
            every box is already at the pickup point.
    """

    copies: list[_CopyLike]
    source_point_id: int | None


def plan_fulfilment(
    free_copies: Sequence[_CopyLike],
    needed: Mapping[int, int],
    pickup_point_id: int,
) -> FulfilmentPlan:
    """Pick boxes for the requested games.

    Args:
        free_copies: Boxes that are on a shelf and not held by another order.
        needed: Requested quantity per catalog game id.
        pickup_point_id: Point where the client will collect the games.

    Returns:
        The chosen boxes and, if any must travel, their single source point.

    Raises:
        NotAvailableError: A game has too few free boxes, or the boxes that
            must travel are spread over several points.
    """
    by_game: dict[int, list[_CopyLike]] = defaultdict(list)
    for copy in sorted(free_copies, key=lambda c: c.id):
        by_game[copy.game_id].append(copy)

    chosen: list[_CopyLike] = []
    remote_need: dict[int, int] = {}
    uncovered: list[int] = []

    for game_id, quantity in needed.items():
        pool = by_game.get(game_id, [])
        if len(pool) < quantity:
            uncovered.append(game_id)
            continue
        local = [c for c in pool if c.current_point_id == pickup_point_id]
        local = local[:quantity]
        chosen.extend(local)
        if quantity > len(local):
            remote_need[game_id] = quantity - len(local)

    if uncovered:
        raise NotAvailableError(uncovered)
    if not remote_need:
        return FulfilmentPlan(copies=chosen, source_point_id=None)

    source_points = sorted({
        c.current_point_id
        for game_id in remote_need
        for c in by_game[game_id]
        if c.current_point_id not in (None, pickup_point_id)
    })
    for point_id in source_points:
        picked: list[_CopyLike] = []
        for game_id, quantity in remote_need.items():
            here = [c for c in by_game[game_id] if c.current_point_id == point_id]
            if len(here) < quantity:
                break
            picked.extend(here[:quantity])
        else:
            return FulfilmentPlan(
                copies=chosen + picked,
                source_point_id=point_id,
            )

    raise NotAvailableError(
        list(remote_need),
        "boxes would have to come from several pickup points",
    )
