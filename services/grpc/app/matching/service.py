"""gRPC matching servicer."""

import logging

import grpc

from app.config import settings
from app.generated.matching.v1 import matching_pb2, matching_pb2_grpc
from app.matching.scoring import Candidate, Meeting, rank

logger = logging.getLogger(__name__)


class MatchingServicer(matching_pb2_grpc.MatchingServiceServicer):
    """Serves MatchingService. Stateless: the caller sends the candidates."""

    async def RankGames(
        self,
        request: matching_pb2.RankGamesRequest,
        context: grpc.aio.ServicerContext,
    ) -> matching_pb2.RankGamesResponse:
        """Rank candidate games for a meeting.

        Algorithm:
            1. Validate the meeting (``INVALID_ARGUMENT`` unless both the
               player count and the time limit are positive).
            2. Reject candidates that cannot serve the meeting: wrong player
               count, no free box, play time far over the limit.
            3. Score the rest (see ``app.matching.scoring``).
            4. Sort by score desc, then shelf availability, then game id;
               trim to the requested limit (``settings.grpc_default_limit``
               when ``limit`` is 0).
        """
        if request.players < 1 or request.max_playtime_minutes < 1:
            await context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                "players and max_playtime_minutes must be positive",
            )

        meeting = Meeting(
            players=request.players,
            max_playtime_minutes=request.max_playtime_minutes,
            preferred_category_ids=frozenset(request.preferred_category_ids),
        )
        candidates = [
            Candidate(
                game_id=c.game_id,
                min_players=c.min_players,
                max_players=c.max_players,
                playtime_minutes=c.playtime_minutes,
                category_ids=frozenset(c.category_ids),
                free_at_point=c.free_at_point,
                free_elsewhere=c.free_elsewhere,
            )
            for c in request.candidates
        ]
        limit = request.limit or settings.grpc_default_limit
        ranked = rank(meeting, candidates, limit)

        logger.info(
            "RankGames players=%s max_playtime=%s candidates=%s returned=%s",
            request.players, request.max_playtime_minutes,
            len(candidates), len(ranked),
        )
        return matching_pb2.RankGamesResponse(
            games=[
                matching_pb2.RankedGame(
                    game_id=candidate.game_id, score=score, reason=reason,
                )
                for candidate, score, reason in ranked
            ],
        )
