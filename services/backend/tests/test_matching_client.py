"""Tests for the matching gRPC client against an in-process fake server."""

import grpc
import pytest
import pytest_asyncio

from app.config import settings
from app.grpc_generated.matching.v1 import matching_pb2, matching_pb2_grpc
from app.integrations.grpc.matching_client import MatchingClient
from app.services.catalog import MatchCandidate, RankedGame
from app.services.exceptions import ServiceUnavailableError


class _FakeMatching(matching_pb2_grpc.MatchingServiceServicer):
    """Records the last request and ranks candidates in reverse order."""

    def __init__(self) -> None:
        self.last_request: matching_pb2.RankGamesRequest | None = None

    async def RankGames(self, request, context):
        self.last_request = request
        return matching_pb2.RankGamesResponse(games=[
            matching_pb2.RankedGame(
                game_id=c.game_id, score=0.5, reason="fits_meeting",
            )
            for c in reversed(request.candidates)
        ])


@pytest_asyncio.fixture
async def fake_matching():
    servicer = _FakeMatching()
    server = grpc.aio.server()
    matching_pb2_grpc.add_MatchingServiceServicer_to_server(servicer, server)
    port = server.add_insecure_port("localhost:0")
    await server.start()
    async with grpc.aio.insecure_channel(f"localhost:{port}") as channel:
        yield MatchingClient(channel), servicer
    await server.stop(grace=0)


def _candidate(game_id: int) -> MatchCandidate:
    return MatchCandidate(
        game_id=game_id, min_players=2, max_players=6, playtime_minutes=60,
        category_ids=[7, 8], free_at_point=1, free_elsewhere=2,
    )


async def test_sends_the_meeting_and_maps_the_ranking(fake_matching):
    client, servicer = fake_matching

    ranked = await client.rank_games(
        players=4,
        max_playtime_minutes=90,
        preferred_category_ids=[7],
        candidates=[_candidate(1), _candidate(2)],
        limit=5,
    )

    request = servicer.last_request
    assert request.players == 4
    assert request.max_playtime_minutes == 90
    assert list(request.preferred_category_ids) == [7]
    assert request.limit == 5
    first = request.candidates[0]
    assert (first.game_id, first.free_at_point, first.free_elsewhere) == (1, 1, 2)
    assert list(first.category_ids) == [7, 8]
    assert ranked == [
        RankedGame(game_id=2, score=0.5, reason="fits_meeting"),
        RankedGame(game_id=1, score=0.5, reason="fits_meeting"),
    ]


async def test_unreachable_server_raises_service_unavailable(monkeypatch):
    monkeypatch.setattr(settings, "grpc_timeout_seconds", 0.2)
    async with grpc.aio.insecure_channel("127.0.0.1:1") as channel:
        client = MatchingClient(channel)
        with pytest.raises(ServiceUnavailableError):
            await client.rank_games(4, 90, [], [_candidate(1)], 5)
