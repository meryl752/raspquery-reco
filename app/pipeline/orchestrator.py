"""
Orchestrateur — parité stackai/lib/agents/orchestrator.ts
"""

from __future__ import annotations

import asyncio
import logging
import time

from app.core.config import Settings, get_settings
from app.core.constants import BUDGET_MAP
from app.core.models import OrchestratorMeta, OrchestratorResult, UserContext, VectorAgent
from app.domain.catalog_filter import filter_catalog_agents
from app.infra.embeddings import generate_embedding
from app.infra.llm import create_llm_client
from app.infra.supabase import get_agents_by_categories, vector_search_agents
from app.pipeline.dry_run import dry_run_result
from app.pipeline.matcher import match_agents
from app.pipeline.query_analyzer import analyze_query
from app.pipeline.retrieval_pool import MIN_POOL_AFTER_ICP, merge_category_agents
from app.pipeline.retrieval_text import build_retrieval_embedding_text
from app.pipeline.stack_builder import build_stack

logger = logging.getLogger(__name__)

ORCHESTRATOR_TIMEOUT_S = 120


def _adapt_fallback_agents(agents: list[VectorAgent]) -> list[VectorAgent]:
    """similarity=1 pour que le matcher s'appuie sur le score métier."""
    return [
        a.model_copy(update={"similarity": 1.0}) if hasattr(a, "model_copy") else a
        for a in agents
    ]


async def run_orchestrator(
    ctx: UserContext,
    settings: Settings | None = None,
) -> OrchestratorResult | None:
    settings = settings or get_settings()
    start = time.perf_counter()

    if settings.reco_dry_run:
        elapsed = int((time.perf_counter() - start) * 1000)
        return dry_run_result(ctx, elapsed)

    llm = create_llm_client(settings)

    async def _pipeline() -> OrchestratorResult | None:
        logger.info("[orchestrator] étape 1 — analyse")
        analyzed = await analyze_query(ctx, llm, settings)

        budget_max = BUDGET_MAP.get(ctx.budget, 0)
        vector_agents: list[VectorAgent] = []
        retrieval_mode: str = "fallback"
        embedding_latency_ms = 0

        try:
            logger.info("[orchestrator] étapes 2-3 — embedding + RPC")
            emb_text = build_retrieval_embedding_text(ctx, analyzed)
            vector, embedding_latency_ms = await generate_embedding(settings, emb_text)
            raw = await vector_search_agents(settings, vector, budget_max, category=None)
            if not raw:
                raise RuntimeError("RPC vectoriel vide")
            filtered = filter_catalog_agents(raw)
            if not filtered:
                raise RuntimeError("Tous les agents exclus par catalog-filter")
            if len(filtered) < MIN_POOL_AFTER_ICP:
                db_agents = await get_agents_by_categories(
                    settings, analyzed.required_category_values
                )
                supplement = filter_catalog_agents(_adapt_fallback_agents(db_agents))
                vector_agents = merge_category_agents(filtered, supplement)
            else:
                vector_agents = filtered
            retrieval_mode = "vector"
            logger.info("[orchestrator] mode vectoriel — %d agents", len(vector_agents))
        except Exception as exc:
            logger.warning("[orchestrator] fallback catégories — %s", exc)
            db_agents = await get_agents_by_categories(
                settings, analyzed.required_category_values
            )
            vector_agents = filter_catalog_agents(_adapt_fallback_agents(db_agents))
            retrieval_mode = "fallback"
            if not vector_agents:
                logger.error("[orchestrator] aucun agent après fallback")
                return None
            logger.info("[orchestrator] mode fallback — %d agents", len(vector_agents))

        logger.info("[orchestrator] étape 4 — matcher")
        candidates = match_agents(vector_agents, analyzed, ctx)
        if not candidates:
            logger.error("[orchestrator] aucun candidat après matcher")
            return None

        delay_s = max(0, settings.reco_llm_step_delay_ms) / 1000.0
        if delay_s > 0:
            logger.info(
                "[orchestrator] pause %.1fs avant stack builder (quota LLM)", delay_s
            )
            await asyncio.sleep(delay_s)

        logger.info("[orchestrator] étape 5 — stack builder")
        top15 = candidates[:15]
        stack = await build_stack(ctx, analyzed, top15, llm)
        if not stack:
            return None

        by_id = {str(a.id): a for a in vector_agents}
        enriched_agents = []
        for agent in stack.agents:
            src = by_id.get(str(agent.id))
            enriched_agents.append(
                agent.model_copy(
                    update={
                        "website_domain": src.website_domain if src else agent.website_domain,
                        "logo_url": (src.logo_url if src else None) or agent.logo_url,
                        "url": (
                            (src.website_url if src else None)
                            or agent.url
                        ),
                        "price_from": src.price_from if src else agent.price_from,
                        "setup_difficulty": (
                            src.setup_difficulty if src else agent.setup_difficulty
                        ),
                        "time_to_value": src.time_to_value if src else agent.time_to_value,
                    }
                )
            )
        stack.agents = enriched_agents

        elapsed = int((time.perf_counter() - start) * 1000)
        return OrchestratorResult(
            stack=stack,
            meta=OrchestratorMeta(
                agents_analyzed=len(vector_agents),
                agents_shortlisted=len(candidates),
                subtasks_detected=len(analyzed.subtasks),
                processing_time_ms=elapsed,
                retrieval_mode=retrieval_mode,  # type: ignore[arg-type]
                embedding_latency_ms=embedding_latency_ms,
            ),
        )

    try:
        return await asyncio.wait_for(_pipeline(), timeout=ORCHESTRATOR_TIMEOUT_S)
    except asyncio.TimeoutError:
        logger.error("[orchestrator] timeout %ss", ORCHESTRATOR_TIMEOUT_S)
        return None
