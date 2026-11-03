"""Domain types used by the recommendation engine."""

from dataclasses import dataclass


@dataclass(frozen=True)
class GameContent:
    """Numeric and categorical features of a game used for similarity.

    Attributes:
        game_id: Catalog game id.
        category_ids: All category ids linked to the game.
        min_players: Minimum supported player count.
        max_players: Maximum supported player count.
        playtime_minutes: Average playtime in minutes.
    """

    game_id: int
    category_ids: frozenset[int]
    min_players: int
    max_players: int
    playtime_minutes: int