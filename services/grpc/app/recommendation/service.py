"""gRPC recommendation servicer."""

import logging

import grpc

from app.config import settings
from app.db import SessionFactory
from app.generated.recommendation.v1 import (
    recommendation_pb2,
    recommendation_pb2_grpc,
)
from app.recommendation.repository import (
    get_cooccurrence,
    get_game_content,
    get_popularity,
)
from app.recommendation.similarity import combined_score, content_similarity

logger = logging.getLogger(__name__)


class RecommendationServicer(
    recommendation_pb2_grpc.RecommendationServiceServicer,
):
    """Serves RecommendationService."""

    async def GetSimilarGames(
        self,
        request: recommendation_pb2.GetSimilarGamesRequest,
        context: grpc.aio.ServicerContext,
    ) -> recommendation_pb2.GetSimilarGamesResponse:
        """Return games similar to ``target_game_id``.

        Algorithm:
            1. Verify that the target game exists (``NOT_FOUND`` otherwise).
            2. Fetch its content features (categories, players, playtime).
            3. Fetch co-occurrence with the target; take the top
               ``max_candidates`` by raw co-occurrence (cheap pre-filter
               before scoring and feature fetch).
            4. For the target and remaining candidates, fetch popularity
               (completed rentals) and content features.
            5. Score each candidate with ``combined_score``; drop any with
               score 0 or present in ``exclude_game_ids``.
            6. Sort by score desc, tie-break by game_id.
            7. Apply the diversity cap: at most 2 games per category.
            8. Trim to the requested limit (``settings.grpc_default_limit``
               when ``limit`` is 0).
        """
        async with SessionFactory() as session:
            target_content = (
                await get_game_content(session, [request.target_game_id])
            ).get(request.target_game_id)
            if target_content is None:
                await context.abort(
                    grpc.StatusCode.NOT_FOUND,
                    f"board game {request.target_game_id} not found",
                )

            cooc_by_game = await get_cooccurrence(
                session, request.target_game_id,
            )
            cooc_by_game.pop(request.target_game_id, None)

            if not cooc_by_game:
                return recommendation_pb2.GetSimilarGamesResponse()

            ranked = sorted(cooc_by_game.items(), key=lambda kv: -kv[1])
            candidate_ids = [
                game_id for game_id, _ in ranked[:settings.grpc_max_candidates]
            ]
            cooc_by_game = {gid: cooc_by_game[gid] for gid in candidate_ids}

            all_ids = [request.target_game_id, *candidate_ids]
            contents = await get_game_content(session, all_ids)
            pops = await get_popularity(session, all_ids)

            target_pop = pops.get(request.target_game_id, 0)
            excluded = set(request.exclude_game_ids)
            excluded.add(request.target_game_id)

            scored: list[tuple[float, str, int, frozenset[int]]] = []
            for game_id in candidate_ids:
                if game_id in excluded:
                    continue
                cand_content = contents.get(game_id)
                if cand_content is None:
                    continue

                content = content_similarity(target_content, cand_content)
                score, reason = combined_score(
                    cooc=cooc_by_game[game_id],
                    pop_target=target_pop,
                    pop_candidate=pops.get(game_id, 0),
                    content=content,
                )
                if score <= 0.0:
                    continue

                scored.append(
                    (score, reason, game_id, cand_content.category_ids),
                )

            scored.sort(key=lambda item: (-item[0], item[2]))

            limit = request.limit or settings.grpc_default_limit
            per_category: dict[int, int] = {}
            results: list[recommendation_pb2.GameRecommendation] = []

            for score, reason, game_id, categories in scored:
                if len(results) >= limit:
                    break
                if categories and any(
                    per_category.get(cat, 0) >= 2 for cat in categories
                ):
                    continue

                results.append(recommendation_pb2.GameRecommendation(
                    game_id=game_id,
                    score=score,
                    reason=reason,
                ))
                for cat in categories:
                    per_category[cat] = per_category.get(cat, 0) + 1

            logger.info(
                "GetSimilarGames target=%s candidates=%s returned=%s",
                request.target_game_id, len(candidate_ids), len(results),
            )
            return recommendation_pb2.GetSimilarGamesResponse(games=results)

    async def GetPersonalRecommendations(
        self,
        request: recommendation_pb2.GetPersonalRecommendationsRequest,
        context: grpc.aio.ServicerContext,
    ) -> recommendation_pb2.GetPersonalRecommendationsResponse:
        await context.abort(
            grpc.StatusCode.UNIMPLEMENTED,
            "GetPersonalRecommendations is not implemented yet",
        )