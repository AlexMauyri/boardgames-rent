"""Tests for MatchingService over an in-process gRPC server (no database)."""

import grpc
import pytest

from app.generated.matching.v1 import matching_pb2, matching_pb2_grpc


def _candidate(game_id: int, *, at_point: int = 1, elsewhere: int = 0,
               players=(2, 6), playtime: int = 60, categories=()):
    return matching_pb2.GameCandidate(
        game_id=game_id,
        min_players=players[0],
        max_players=players[1],
        playtime_minutes=playtime,
        category_ids=categories,
        free_at_point=at_point,
        free_elsewhere=elsewhere,
    )


async def _call(port: int, request: matching_pb2.RankGamesRequest):
    async with grpc.aio.insecure_channel(f"localhost:{port}") as channel:
        stub = matching_pb2_grpc.MatchingServiceStub(channel)
        return await stub.RankGames(request, timeout=2.0)


async def test_ranks_fitting_games_and_drops_the_rest(grpc_server):
    resp = await _call(grpc_server, matching_pb2.RankGamesRequest(
        players=4,
        max_playtime_minutes=90,
        candidates=[
            _candidate(1, at_point=0, elsewhere=1),
            _candidate(2),
            _candidate(3, players=(5, 8)),
            _candidate(4, playtime=200),
        ],
    ))

    assert [g.game_id for g in resp.games] == [2, 1]
    assert resp.games[0].reason == "fits_meeting"
    assert resp.games[1].reason == "needs_delivery"
    assert resp.games[0].score > resp.games[1].score > 0


async def test_preferred_categories_lift_matching_games(grpc_server):
    resp = await _call(grpc_server, matching_pb2.RankGamesRequest(
        players=4,
        max_playtime_minutes=90,
        preferred_category_ids=[7],
        candidates=[_candidate(1), _candidate(2, categories=[7])],
    ))

    assert [g.game_id for g in resp.games] == [2, 1]
    assert resp.games[0].reason == "category_match"


async def test_limit_is_applied(grpc_server):
    resp = await _call(grpc_server, matching_pb2.RankGamesRequest(
        players=4,
        max_playtime_minutes=90,
        limit=2,
        candidates=[_candidate(i) for i in range(1, 6)],
    ))

    assert [g.game_id for g in resp.games] == [1, 2]


async def test_no_candidates_gives_empty_response(grpc_server):
    resp = await _call(grpc_server, matching_pb2.RankGamesRequest(
        players=4, max_playtime_minutes=90,
    ))

    assert list(resp.games) == []


@pytest.mark.parametrize(
    ("players", "minutes"), [(0, 90), (4, 0)], ids=["no-players", "no-time"],
)
async def test_invalid_meeting_is_rejected(grpc_server, players, minutes):
    with pytest.raises(grpc.aio.AioRpcError) as exc:
        await _call(grpc_server, matching_pb2.RankGamesRequest(
            players=players, max_playtime_minutes=minutes,
        ))

    assert exc.value.code() == grpc.StatusCode.INVALID_ARGUMENT
