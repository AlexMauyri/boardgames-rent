"""Client for the game matching gRPC service."""

import logging
from collections.abc import Sequence

import grpc
import grpc.aio

from app.config import settings
from app.grpc_generated.matching.v1 import matching_pb2, matching_pb2_grpc
from app.services.catalog import MatchCandidate, RankedGame
from app.services.exceptions import ServiceUnavailableError

logger = logging.getLogger(__name__)


class MatchingClient:
    """Typed stub for ``MatchingService`` over a shared channel."""

    def __init__(self, channel: grpc.aio.Channel) -> None:
        self._stub = matching_pb2_grpc.MatchingServiceStub(channel)

    async def rank_games(
        self,
        players: int,
        max_playtime_minutes: int,
        preferred_category_ids: Sequence[int],
        candidates: Sequence[MatchCandidate],
        limit: int,
    ) -> list[RankedGame]:
        """Rank ``candidates`` for the meeting, best first.

        Raises:
            ServiceUnavailableError: The gRPC call failed.
        """
        request = matching_pb2.RankGamesRequest(
            players=players,
            max_playtime_minutes=max_playtime_minutes,
            preferred_category_ids=preferred_category_ids,
            limit=limit,
            candidates=[
                matching_pb2.GameCandidate(
                    game_id=c.game_id,
                    min_players=c.min_players,
                    max_players=c.max_players,
                    playtime_minutes=c.playtime_minutes,
                    category_ids=c.category_ids,
                    free_at_point=c.free_at_point,
                    free_elsewhere=c.free_elsewhere,
                )
                for c in candidates
            ],
        )
        try:
            response = await self._stub.RankGames(
                request, timeout=settings.grpc_timeout_seconds,
            )
        except grpc.aio.AioRpcError as exc:
            logger.warning("gRPC RankGames failed code=%s", exc.code())
            raise ServiceUnavailableError("Matching service unavailable") from exc
        return [
            RankedGame(game_id=g.game_id, score=g.score, reason=g.reason)
            for g in response.games
        ]
