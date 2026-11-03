"""Tests for the pure meeting-to-game scoring (no database, no gRPC)."""

import pytest

from app.matching.scoring import (
    REASON_CATEGORY,
    REASON_DELIVERY,
    REASON_FITS,
    REASON_LONG,
    Candidate,
    Meeting,
    rank,
    score_candidate,
)


def _game(
    game_id: int = 1,
    *,
    players: tuple[int, int] = (2, 6),
    playtime: int = 60,
    categories: frozenset[int] = frozenset(),
    at_point: int = 1,
    elsewhere: int = 0,
) -> Candidate:
    return Candidate(
        game_id=game_id,
        min_players=players[0],
        max_players=players[1],
        playtime_minutes=playtime,
        category_ids=categories,
        free_at_point=at_point,
        free_elsewhere=elsewhere,
    )


MEETING = Meeting(players=4, max_playtime_minutes=90)


@pytest.mark.parametrize("players", [(5, 8), (1, 3)])
def test_wrong_player_count_is_rejected(players):
    assert score_candidate(MEETING, _game(players=players)) is None


def test_game_without_free_boxes_is_rejected():
    assert score_candidate(MEETING, _game(at_point=0, elsewhere=0)) is None


def test_play_time_far_over_the_limit_is_rejected():
    assert score_candidate(MEETING, _game(playtime=120)) is None


def test_play_time_slightly_over_the_limit_is_kept_but_marked():
    result = score_candidate(MEETING, _game(playtime=100))

    assert result is not None
    assert result[1] == REASON_LONG


def test_fitting_game_on_the_shelf_scores_full_marks_in_the_middle():
    score, reason = score_candidate(MEETING, _game(players=(2, 6), playtime=60))

    assert score == pytest.approx(1.0)
    assert reason == REASON_FITS


def test_game_to_be_delivered_scores_lower_with_its_own_reason():
    on_shelf = score_candidate(MEETING, _game(at_point=1))
    delivered = score_candidate(MEETING, _game(at_point=0, elsewhere=2))

    assert delivered[0] < on_shelf[0]
    assert delivered[1] == REASON_DELIVERY


def test_very_short_game_scores_lower_than_one_that_uses_the_time():
    fills = score_candidate(MEETING, _game(playtime=80))
    brief = score_candidate(MEETING, _game(playtime=10))

    assert brief[0] < fills[0]


def test_group_at_the_edge_of_the_range_scores_lower_than_in_the_middle():
    middle = score_candidate(MEETING, _game(players=(2, 6)))
    edge = score_candidate(MEETING, _game(players=(4, 8)))

    assert edge[0] < middle[0]


def test_category_preference_rewards_matching_games():
    meeting = Meeting(4, 90, frozenset({1, 2}))
    both = score_candidate(meeting, _game(categories=frozenset({1, 2})))
    one = score_candidate(meeting, _game(categories=frozenset({1})))
    none = score_candidate(meeting, _game(categories=frozenset({3})))

    assert both[0] > one[0] > none[0]
    assert both[1] == REASON_CATEGORY
    assert none[1] == REASON_FITS


def test_without_preference_categories_do_not_matter():
    plain = score_candidate(MEETING, _game())
    tagged = score_candidate(MEETING, _game(categories=frozenset({7})))

    assert plain[0] == pytest.approx(tagged[0])


def test_rank_orders_best_first_and_drops_rejected():
    games = [
        _game(1, at_point=0, elsewhere=1),
        _game(2),
        _game(3, players=(5, 8)),
    ]

    result = rank(MEETING, games, limit=10)

    assert [c.game_id for c, _, _ in result] == [2, 1]


def test_rank_breaks_ties_by_game_id():
    result = rank(MEETING, [_game(9), _game(4)], limit=10)

    assert [c.game_id for c, _, _ in result] == [4, 9]


def test_rank_trims_to_limit():
    result = rank(MEETING, [_game(i) for i in range(1, 6)], limit=2)

    assert [c.game_id for c, _, _ in result] == [1, 2]
