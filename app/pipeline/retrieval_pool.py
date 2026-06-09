"""Renforce le pool vectoriel si le filtre ICP laisse trop peu de candidats."""

from __future__ import annotations

import logging

from app.core.models import VectorAgent

logger = logging.getLogger(__name__)

MIN_POOL_AFTER_ICP = 12


def merge_category_agents(
    vector_agents: list[VectorAgent],
    category_agents: list[VectorAgent],
    *,
    min_pool: int = MIN_POOL_AFTER_ICP,
) -> list[VectorAgent]:
    if len(vector_agents) >= min_pool or not category_agents:
        return vector_agents

    seen = {str(a.id) for a in vector_agents}
    merged = list(vector_agents)
    added = 0

    for agent in category_agents:
        aid = str(agent.id)
        if aid in seen:
            continue
        merged.append(agent)
        seen.add(aid)
        added += 1
        if len(merged) >= min_pool:
            break

    if added:
        logger.info(
            "retrieval: pool complété par catégories (+ %d, total %d)",
            added,
            len(merged),
        )
    return merged
