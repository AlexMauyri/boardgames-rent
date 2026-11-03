"""Unit tests for the pure similarity functions.

No database, no gRPC. GameContent fixtures are built inline.
"""
import pytest

from app.recommendation.similarity import (
    combined_score,
    content_similarity,
)
from app.recommendation.types import GameContent


def _game(
    game_id: int = 1,
    *,
    categories: frozenset[int] = frozenset(),
    min_players: int = 1,
    max_players: int = 4,
    playtime_minutes: int = 60,
) -> GameContent:
    return GameContent(
        game_id=game_id,
        category_ids=categories,
        min_players=min_players,
        max_players=max_players,
        playtime_minutes=playtime_minutes,
    )


# ---------------------------------------------------------------------------
# content_similarity
# ---------------------------------------------------------------------------


def test_identical_games_score_one():
    g = _game(categories=frozenset({1, 2}))
    assert content_similarity(g, g) == 1.0


def test_disjoint_games_score_near_zero():
    a = _game(categories=frozenset({1}), min_players=1, max_players=2, playtime_minutes=15)
    b = _game(categories=frozenset({2}), min_players=8, max_players=12, playtime_minutes=180)
    # Categories disjoint, player ranges disjoint, playtime far apart.
    assert content_similarity(a, b) < 0.05


def test_empty_categories_do_not_count_as_match():
    """Two games without categories are not "similar" on that axis."""
    a = _game(categories=frozenset())
    b = _game(categories=frozenset())
    # Only player and playtime components contribute; jaccard = 0.
    score = content_similarity(a, b)
    assert score == 0.3 * 1.0 + 0.2 * 1.0  # players overlap = 1, playtime = 1


def test_partial_category_overlap():
    a = _game(categories=frozenset({1, 2}))
    b = _game(categories=frozenset({2, 3}))
    # Jaccard = 1/3. Players and playtime are identical in the fixture,
    # so they contribute 0.3 * 1.0 + 0.2 * 1.0 = 0.5.
    score = content_similarity(a, b)
    assert score == pytest.approx(0.5 * (1 / 3) + 0.5)


def test_player_range_overlap():
    a = _game(min_players=2, max_players=4)
    b = _game(min_players=3, max_players=6)
    # Overlap [3,4] length 2, union [2,6] length 5.
    # Jaccard=0, players=0.4, playtime=1.0 → 0.3*0.4 + 0.2*1.0 = 0.32.
    assert content_similarity(a, b) == 0.32


def test_player_range_disjoint():
    a = _game(min_players=1, max_players=2)
    b = _game(min_players=5, max_players=8)
    # Jaccard=0, players=0, playtime=1.0 → 0.2 * 1.0 = 0.2.
    score = content_similarity(a, b)
    assert score == 0.2


def test_playtime_proximity_exact():
    a = _game(playtime_minutes=60)
    b = _game(playtime_minutes=60)
    # Empty categories → 0. Identical players and playtime → 0.3 + 0.2.
    assert content_similarity(a, b) == 0.5


def test_playtime_proximity_far():
    a = _game(playtime_minutes=15)
    b = _game(playtime_minutes=180)
    # Playtime proximity = 1 - 165/180 ≈ 0.083.
    # Players overlap = 1.0 (same 1–4 range), contributing 0.3.
    # Total = 0.3 + 0.2 * 0.083 ≈ 0.3167.
    score = content_similarity(a, b)
    assert 0.3 < score < 0.32


def test_playtime_zero_does_not_divide_by_zero():
    a = _game(playtime_minutes=0)
    b = _game(playtime_minutes=0)
    # max is 0 → _playtime_proximity returns 0.0.
    assert content_similarity(a, b) == 0.3 * 1.0  # players only


# ---------------------------------------------------------------------------
# combined_score: guards and weights
# ---------------------------------------------------------------------------


def test_cold_start_both_popularities_zero():
    """Neither game has been rented → cooc signal is dropped, content drives."""
    score, reason = combined_score(
        cooc=0, pop_target=0, pop_candidate=0, content=0.7,
    )
    assert score == 0.7
    assert reason == "similar"


def test_zero_popularity_drops_cooc_signal():
    """Even if cooc > 0, pop = 0 means the normalized cooc is undefined."""
    score, reason = combined_score(
        cooc=3, pop_target=0, pop_candidate=5, content=0.5,
    )
    assert score == 0.5
    assert reason == "similar"


def test_strong_cooc_uses_heavy_weight():
    score, reason = combined_score(
        cooc=10, pop_target=20, pop_candidate=20, content=0.5,
    )
    # cooc_score = 10 / sqrt(400) = 0.5.
    # score = 0.8 * 0.5 + 0.2 * 0.5 = 0.5.
    assert score == 0.5
    assert reason == "bought_together"


def test_weak_cooc_uses_balanced_weight():
    score, reason = combined_score(
        cooc=2, pop_target=20, pop_candidate=20, content=0.5,
    )
    # cooc_score = 2 / 20 = 0.1.
    # score = 0.5 * 0.1 + 0.5 * 0.5 = 0.3.
    assert score == 0.3
    assert reason == "bought_together"


def test_cooc_without_content_still_bought_together():
    score, reason = combined_score(
        cooc=2, pop_target=20, pop_candidate=20, content=0.0,
    )
    assert score == 0.5 * 0.1  # 0.05
    assert reason == "bought_together"


def test_no_signal_at_all():
    score, reason = combined_score(
        cooc=0, pop_target=0, pop_candidate=0, content=0.0,
    )
    assert score == 0.0
    assert reason == ""


def test_content_only_fallback():
    score, reason = combined_score(
        cooc=0, pop_target=5, pop_candidate=5, content=0.75,
    )
    assert score == 0.75
    assert reason == "similar"


def test_cooc_score_is_clamped():
    """cooc / sqrt(pop_a * pop_b) can exceed 1; clamp to 1."""
    # A pathological case: cooc = 10, pop = 5, 5 → sqrt(25) = 5 → 10/5 = 2.
    score, _ = combined_score(
        cooc=10, pop_target=5, pop_candidate=5, content=0.0,
    )
    # cooc_score clamped to 1.0; cooc=10 >= 5 → strong mix.
    assert score == 0.8 * 1.0 + 0.2 * 0.0  # 0.8