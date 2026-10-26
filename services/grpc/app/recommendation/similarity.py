"""Pure similarity functions for the recommendation engine.

No database access, no gRPC imports — only ``GameContent`` from
``app.recommendation.types``. This module is the heart of both RPCs:
``GetSimilarGames`` and ``GetPersonalRecommendations`` both rank
candidates through ``combined_score``.

The formula intentionally mixes two signals:

* co-occurrence — how often two games were rented together;
* content — how similar their categories, player counts and playtimes
  are.

The mix is adaptive: when co-occurrence is weak, content similarity
takes over, so cold-start games (never rented) still get recommendations.
"""

import math

from app.recommendation.types import GameContent

# Weights for the content similarity sub-score. They sum to 1.0.
_CAT_WEIGHT = 0.5
_PLAYERS_WEIGHT = 0.3
_PLAYTIME_WEIGHT = 0.2

# Co-occurrence thresholds that switch the weight mix.
_STRONG_COOC_THRESHOLD = 5
_STRONG_COOC_MIX = (0.8, 0.2)   # (cooc weight, content weight)
_WEAK_COOC_MIX = (0.5, 0.5)


def _jaccard(a: frozenset[int], b: frozenset[int]) -> float:
    """Jaccard similarity of two sets.

    Returns 0.0 when both sets are empty: two games without categories
    are not "100% similar" just because their category sets are equal.
    """
    if not a and not b:
        return 0.0
    union = len(a | b)
    if union == 0:
        return 0.0
    return len(a & b) / union


def _players_overlap(a: GameContent, b: GameContent) -> float:
    """Length of the overlapping player range divided by the union range.

    Both ranges are inclusive. Example: [2, 4] and [3, 6] overlap on
    [3, 4] (length 2); union is [2, 6] (length 5); score = 0.4.
    """
    lo = max(a.min_players, b.min_players)
    hi = min(a.max_players, b.max_players)
    overlap = max(0, hi - lo + 1)
    union = max(a.max_players, b.max_players) - min(
        a.min_players, b.min_players,
    ) + 1
    if union <= 0:
        return 0.0
    return overlap / union


def _playtime_proximity(a: GameContent, b: GameContent) -> float:
    """1 − |a − b| / max(a, b). Identical playtime gives 1.0."""
    worst = max(a.playtime_minutes, b.playtime_minutes)
    if worst <= 0:
        return 0.0
    diff = abs(a.playtime_minutes - b.playtime_minutes)
    return 1.0 - (diff / worst)


def content_similarity(a: GameContent, b: GameContent) -> float:
    """Similarity between two games based on categories, players, playtime.

    Returns a value in ``[0.0, 1.0]``. Equal category sets, overlapping
    player ranges, and close playtime push the score towards 1.0.
    Completely disjoint features push it towards 0.0.
    """
    return (
        _CAT_WEIGHT * _jaccard(a.category_ids, b.category_ids)
        + _PLAYERS_WEIGHT * _players_overlap(a, b)
        + _PLAYTIME_WEIGHT * _playtime_proximity(a, b)
    )


def combined_score(
    cooc: int,
    pop_target: int,
    pop_candidate: int,
    content: float,
) -> tuple[float, str]:
    """Combine co-occurrence and content similarity into one score and reason.

    Args:
        cooc: Number of distinct completed orders where target and
            candidate were rented together.
        pop_target: Number of completed rentals of the target game.
        pop_candidate: Number of completed rentals of the candidate.
        content: ``content_similarity`` between target and candidate.

    Returns:
        ``(score, reason)``. ``score`` is in ``[0.0, 1.0]``.
        ``reason`` is one of ``"bought_together"``, ``"similar"``, or
        ``""`` when the pair has no usable signal at all.
    """
    if pop_target <= 0 or pop_candidate <= 0:
        cooc = 0
        cooc_score = 0.0
    else:
        cooc_score = cooc / math.sqrt(pop_target * pop_candidate)
        cooc_score = min(cooc_score, 1.0)

    if cooc >= _STRONG_COOC_THRESHOLD:
        w_cooc, w_content = _STRONG_COOC_MIX
        score = w_cooc * cooc_score + w_content * content
        return (score, "bought_together")

    if cooc > 0:
        w_cooc, w_content = _WEAK_COOC_MIX
        score = w_cooc * cooc_score + w_content * content
        return (score, "bought_together")

    if content > 0.0:
        return (content, "similar")

    return (0.0, "")