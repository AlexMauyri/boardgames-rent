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
    get_client_history,
    get_cooccurrence,
    get_game_content,
    get_popularity,
    get_top_popular,
)
from app.recommendation.similarity import combined_score, content_similarity
from app.recommendation.types import GameContent

logger = logging.getLogger(__name__)

_POSITION_DECAY = 0.05
_POSITION_FLOOR = 0.2


class RecommendationServicer(
    recommendation_pb2_grpc.RecommendationServiceServicer,
):
    """Serves RecommendationService.

    Both RPCs read from PostgreSQL as ``reader_user`` (SELECT only).
    """

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

            scored: list[tuple[int, float, str]] = []
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

                scored.append((game_id, score, reason))

            scored.sort(key=lambda item: (-item[1], item[0]))
            limit = request.limit or settings.grpc_default_limit
            results = self._apply_diversity_cap(scored, contents, limit)

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
        """Return recommendations tailored to ``client_id``.

        Algorithm:
            1. Fetch the client's history: distinct games from completed
               orders, most recent first (capped at
               ``settings.grpc_max_history_games``).
            2. Empty history → global popularity, reason ``fallback_popular``.
            3. Otherwise, for each game in history, fetch its co-occurrence
               candidates. A candidate that appears in the co-occurrence of
               several history games gets contributions from all of them,
               each weighted by the game's position in history (decay 0.05,
               floor 0.2).
            4. Score every candidate with ``combined_score`` against each
               contributing history game; a candidate's reason is
               ``bought_together`` if any of its sources is ``bought_together``,
               otherwise ``similar``.
            5. If the history exists but no candidate survives, fall back to
               popularity within the history's categories, reason
               ``fallback_popular``.
            6. Sort by accumulated score, apply the diversity cap, trim to
               ``limit``.
        """
        async with SessionFactory() as session:
            limit = request.limit or settings.grpc_default_limit
            excluded = set(request.exclude_game_ids)

            history = await get_client_history(
                session,
                request.client_id,
                settings.grpc_max_history_games,
            )

            if not history:
                return await self._fallback_popular(
                    session, exclude_ids=excluded,
                    category_ids=[], limit=limit,
                )

            history_set = set(history)
            excluded |= history_set
            position = {gid: i for i, gid in enumerate(history)}

            history_contents = await get_game_content(session, history)
            history_pops = await get_popularity(session, history)

            cooc_by_candidate: dict[int, list[tuple[int, int]]] = {}
            for hist_game_id in history:
                cooc_by_game = await get_cooccurrence(session, hist_game_id)
                cooc_by_game.pop(hist_game_id, None)
                for gid, cooc in cooc_by_game.items():
                    if gid in excluded:
                        continue
                    cooc_by_candidate.setdefault(gid, []).append(
                        (hist_game_id, cooc),
                    )

            if not cooc_by_candidate:
                history_categories: set[int] = set()
                for content in history_contents.values():
                    history_categories |= content.category_ids
                return await self._fallback_popular(
                    session, exclude_ids=excluded,
                    category_ids=list(history_categories), limit=limit,
                )

            candidate_ids = list(cooc_by_candidate.keys())
            candidate_contents = await get_game_content(session, candidate_ids)
            all_pops = await get_popularity(session, candidate_ids + history)

            scores: dict[int, float] = {}
            reasons: dict[int, str] = {}
            for gid, cooc_list in cooc_by_candidate.items():
                cand_content = candidate_contents.get(gid)
                if cand_content is None:
                    continue
                total = 0.0
                best_reason = ""
                for hist_game_id, cooc in cooc_list:
                    hist_content = history_contents.get(hist_game_id)
                    if hist_content is None:
                        continue
                    weight = max(
                        1.0 - _POSITION_DECAY * position[hist_game_id],
                        _POSITION_FLOOR,
                    )
                    content_sim = content_similarity(hist_content, cand_content)
                    score, reason = combined_score(
                        cooc=cooc,
                        pop_target=history_pops.get(hist_game_id, 0),
                        pop_candidate=all_pops.get(gid, 0),
                        content=content_sim,
                    )
                    if score <= 0.0:
                        continue
                    total += score * weight
                    if reason == "bought_together":
                        best_reason = "bought_together"
                    elif not best_reason:
                        best_reason = reason
                if total > 0.0 and best_reason:
                    scores[gid] = total
                    reasons[gid] = best_reason

            if not scores:
                history_categories = set()
                for content in history_contents.values():
                    history_categories |= content.category_ids
                return await self._fallback_popular(
                    session, exclude_ids=excluded,
                    category_ids=list(history_categories), limit=limit,
                )

            ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
            results = self._apply_diversity_cap_with_reasons(
                ranked, candidate_contents, reasons, limit,
            )

            logger.info(
                "GetPersonalRecommendations client=%s history=%s "
                "candidates=%s returned=%s",
                request.client_id, len(history),
                len(candidate_ids), len(results),
            )
            return recommendation_pb2.GetPersonalRecommendationsResponse(
                games=results,
            )

    async def _fallback_popular(
        self,
        session,
        *,
        exclude_ids: set[int],
        category_ids: list[int],
        limit: int,
    ) -> recommendation_pb2.GetPersonalRecommendationsResponse:
        """Return top-popular games with reason "fallback_popular"."""
        popular = await get_top_popular(
            session,
            exclude_ids=list(exclude_ids),
            category_ids=category_ids,
            limit=limit,
        )
        if not popular:
            return recommendation_pb2.GetPersonalRecommendationsResponse()
        return recommendation_pb2.GetPersonalRecommendationsResponse(
            games=[
                recommendation_pb2.GameRecommendation(
                    game_id=gid,
                    score=1.0 - i * 0.001,
                    reason="fallback_popular",
                )
                for i, gid in enumerate(popular)
            ],
        )

    def _apply_diversity_cap(
        self,
        scored: list[tuple[int, float, str]],
        contents: dict[int, GameContent],
        limit: int,
    ) -> list[recommendation_pb2.GameRecommendation]:
        """Keep at most 2 games per category, then trim to ``limit``.

        ``scored`` is pre-sorted by (score desc, game_id asc). Games
        without categories always pass — the cap only restricts games
        that would otherwise cluster in a single genre.
        """
        per_category: dict[int, int] = {}
        results: list[recommendation_pb2.GameRecommendation] = []
        for game_id, score, reason in scored:
            if len(results) >= limit:
                break
            content = contents.get(game_id)
            if content is None:
                continue
            if content.category_ids and any(
                per_category.get(cat, 0) >= 2 for cat in content.category_ids
            ):
                continue
            results.append(recommendation_pb2.GameRecommendation(
                game_id=game_id, score=score, reason=reason,
            ))
            for cat in content.category_ids:
                per_category[cat] = per_category.get(cat, 0) + 1
        return results

    def _apply_diversity_cap_with_reasons(
        self,
        ranked: list[tuple[int, float]],
        contents: dict[int, GameContent],
        reasons: dict[int, str],
        limit: int,
    ) -> list[recommendation_pb2.GameRecommendation]:
        """Same diversity cap, for a ranked list without an inline reason.

        Used by ``GetPersonalRecommendations``, where the reason is
        computed once per candidate and stored in a separate mapping.
        """
        scored = [
            (gid, score, reasons.get(gid, ""))
            for gid, score in ranked
        ]
        return self._apply_diversity_cap(scored, contents, limit)