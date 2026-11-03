"""Meeting-to-game matching score.

Pure functions, no database and no gRPC imports. A client describes a
meeting (how many players, how much time, optionally favourite categories);
every candidate game gets a score in ``(0, 1]`` or is rejected outright.

Hard rules (the game is rejected):

* the player count is outside the game's supported range;
* no free box exists anywhere;
* the play time exceeds the limit by more than ``_OVERRUN_TOLERANCE``.

Soft criteria, combined as a weighted mean:

* time fit — full marks when the game fits the limit and uses at least half
  of it, less for a very short game, and falling to zero as it overruns;
* players fit — a game scores best when the group is in the middle of its
  supported range;
* category match — the share of preferred categories the game covers; the
  criterion is dropped when no preference is given;
* availability — a box on the pickup point's shelf beats one that has to be
  delivered.
"""

from dataclasses import dataclass

_OVERRUN_TOLERANCE = 0.25
_SHORT_GAME_RATIO = 0.5
_DELIVERY_AVAILABILITY = 0.6

_TIME_WEIGHT = 0.30
_PLAYERS_WEIGHT = 0.25
_CATEGORY_WEIGHT = 0.25
_AVAILABILITY_WEIGHT = 0.20

REASON_FITS = "fits_meeting"
REASON_CATEGORY = "category_match"
REASON_DELIVERY = "needs_delivery"
REASON_LONG = "slightly_long"


@dataclass(frozen=True)
class Meeting:
    """What the client asked for.

    Attributes:
        players: Number of people who will play, at least 1.
        max_playtime_minutes: Time they have, at least 1.
        preferred_category_ids: Favourite categories; may be empty.
    """

    players: int
    max_playtime_minutes: int
    preferred_category_ids: frozenset[int] = frozenset()


@dataclass(frozen=True)
class Candidate:
    """A game that may be offered.

    Attributes:
        game_id: Catalog id.
        min_players: Lower bound of the supported player count.
        max_players: Upper bound of the supported player count.
        playtime_minutes: Average length of a game.
        category_ids: Categories the game belongs to.
        free_at_point: Free boxes on the chosen pickup point's shelf.
        free_elsewhere: Free boxes at other points.
    """

    game_id: int
    min_players: int
    max_players: int
    playtime_minutes: int
    category_ids: frozenset[int]
    free_at_point: int
    free_elsewhere: int


def _time_score(playtime: int, limit: int) -> float | None:
    """Score the play time, or None when it overruns beyond tolerance."""
    ratio = playtime / limit
    if ratio <= 1.0:
        return 1.0 if ratio >= _SHORT_GAME_RATIO else 0.5 + ratio
    overrun = ratio - 1.0
    if overrun > _OVERRUN_TOLERANCE:
        return None
    return 0.5 * (1.0 - overrun / _OVERRUN_TOLERANCE)


def _players_score(players: int, low: int, high: int) -> float:
    """Score 1.0 in the middle of the supported range, 0.5 at its ends."""
    if high == low:
        return 1.0
    middle = (low + high) / 2
    half_width = (high - low) / 2
    return 1.0 - 0.5 * abs(players - middle) / half_width


def score_candidate(
    meeting: Meeting,
    candidate: Candidate,
) -> tuple[float, str] | None:
    """Score one game for the meeting.

    Args:
        meeting: The client's request.
        candidate: The game to judge.

    Returns:
        ``(score, reason)``, or None when the game is rejected.
    """
    if not candidate.min_players <= meeting.players <= candidate.max_players:
        return None
    if candidate.free_at_point + candidate.free_elsewhere <= 0:
        return None

    time = _time_score(candidate.playtime_minutes, meeting.max_playtime_minutes)
    if time is None:
        return None

    parts = [
        (_TIME_WEIGHT, time),
        (
            _PLAYERS_WEIGHT,
            _players_score(
                meeting.players, candidate.min_players, candidate.max_players,
            ),
        ),
        (
            _AVAILABILITY_WEIGHT,
            1.0 if candidate.free_at_point > 0 else _DELIVERY_AVAILABILITY,
        ),
    ]
    matched = 0
    if meeting.preferred_category_ids:
        matched = len(meeting.preferred_category_ids & candidate.category_ids)
        parts.append(
            (_CATEGORY_WEIGHT, matched / len(meeting.preferred_category_ids)),
        )

    score = round(sum(w * s for w, s in parts) / sum(w for w, _ in parts), 4)

    if candidate.playtime_minutes > meeting.max_playtime_minutes:
        reason = REASON_LONG
    elif candidate.free_at_point == 0:
        reason = REASON_DELIVERY
    elif matched:
        reason = REASON_CATEGORY
    else:
        reason = REASON_FITS
    return score, reason


def rank(
    meeting: Meeting,
    candidates: list[Candidate],
    limit: int,
) -> list[tuple[Candidate, float, str]]:
    """Rank the candidates for the meeting, best first.

    Ties break by shelf availability (collectable at once first), then by
    game id, so the order is deterministic.

    Args:
        meeting: The client's request.
        candidates: Games to judge.
        limit: Maximum number of results.

    Returns:
        Up to ``limit`` tuples of ``(candidate, score, reason)``.
    """
    scored = []
    for candidate in candidates:
        result = score_candidate(meeting, candidate)
        if result is not None:
            scored.append((candidate, *result))
    scored.sort(
        key=lambda item: (-item[1], item[0].free_at_point == 0, item[0].game_id),
    )
    return scored[:limit]
