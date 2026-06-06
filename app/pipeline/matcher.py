"""Hybrid search RRF — réimplémentation autonome (équivalent stackai/lib/agents/matcher.ts)."""

from app.core.constants import (
    BUDGET_MAP,
    DEPENDENCY_INTEGRATION_BONUS,
    DEPENDENCY_INTEGRATION_BONUS_CAP,
    DIFFICULTY_ALLOWED,
    RRF_K,
)
from app.core.models import ScoredAgent, UserContext, VectorAgent
from app.domain.analyzed_query import AnalyzedQuery
from app.domain.task_graph import parent_context_tokens


def _rrf_score(rank_vector: int, rank_business: int) -> float:
    return (1 / (RRF_K + rank_vector)) + (1 / (RRF_K + rank_business))


def _compute_business_score(
    agent: VectorAgent,
    query: AnalyzedQuery,
    ctx: UserContext,
    all_text: str,
    budget_max: int,
    allowed_diff: list[str],
    dependency_tokens: set[str],
) -> float | None:
    if budget_max == 0 and agent.price_from > 0:
        return None
    if budget_max > 0 and agent.price_from > budget_max:
        return None

    score = 0.0

    if agent.category in query.required_category_values:
        score += 20

    use_case_matches = sum(1 for uc in agent.use_cases if uc.lower() in all_text)
    score += min(use_case_matches * 10, 35)

    best_for = agent.best_for or []
    best_for_matches = sum(1 for bf in best_for if bf.lower() in all_text)
    score += min(best_for_matches * 10, 20)

    not_for = agent.not_for or []
    not_for_matches = sum(1 for nf in not_for if nf.lower() in all_text)
    score -= not_for_matches * 20

    integrations = agent.integrations or []
    current_tools_lower = [t.lower() for t in ctx.current_tools]
    integration_matches = sum(
        1
        for intg in integrations
        if any(t in intg.lower() or intg.lower() in t for t in current_tools_lower)
    )
    score += min(integration_matches * 3, 10)

    # Bonus chaîne de dépendances : intégrations alignées sur outils des tâches parentes
    if dependency_tokens and integrations:
        chain_hits = sum(
            1
            for intg in integrations
            if any(tok in intg.lower() or intg.lower() in tok for tok in dependency_tokens)
        )
        if chain_hits > 0:
            score += min(
                chain_hits * DEPENDENCY_INTEGRATION_BONUS,
                DEPENDENCY_INTEGRATION_BONUS_CAP,
            )

    difficulty = agent.setup_difficulty or "easy"
    if difficulty not in allowed_diff:
        score -= 15

    if ctx.timeline == "asap":
        ttv = (agent.time_to_value or "").lower()
        if "semaine" in ttv or "mois" in ttv:
            score -= 10

    return max(0.0, score)


def match_agents(
    agents: list[VectorAgent],
    query: AnalyzedQuery,
    ctx: UserContext,
) -> list[ScoredAgent]:
    budget_max = BUDGET_MAP.get(ctx.budget, 0)
    allowed_diff = DIFFICULTY_ALLOWED.get(ctx.tech_level, ["easy"])
    all_text = " ".join(
        [ctx.objective, *query.subtasks, query.sector_context or ""]
    ).lower()
    dependency_tokens = parent_context_tokens(query)

    with_business: list[tuple[VectorAgent, float]] = []
    for agent in agents:
        business_score = _compute_business_score(
            agent, query, ctx, all_text, budget_max, allowed_diff, dependency_tokens
        )
        if business_score is None:
            continue
        with_business.append((agent, business_score))

    if not with_business:
        return []

    vector_ranks = {agent.id: idx + 1 for idx, (agent, _) in enumerate(with_business)}
    sorted_by_business = sorted(with_business, key=lambda x: x[1], reverse=True)
    business_ranks = {agent.id: idx + 1 for idx, (agent, _) in enumerate(sorted_by_business)}

    fused: list[tuple[VectorAgent, float, int, int, float]] = []
    n = len(with_business)
    for agent, business_score in with_business:
        rank_v = vector_ranks.get(agent.id, n)
        rank_b = business_ranks.get(agent.id, n)
        fused.append((agent, business_score, rank_v, rank_b, _rrf_score(rank_v, rank_b)))

    rrf_values = [item[4] for item in fused]
    max_rrf = max(rrf_values)
    min_rrf = min(rrf_values)
    span = max_rrf - min_rrf or 1.0

    results: list[ScoredAgent] = []
    for agent, _business_score, rank_v, rank_b, rrf in fused:
        relevance_score = round(((rrf - min_rrf) / span) * 100)

        reasons: list[str] = []
        if (agent.similarity or 0) >= 0.7:
            reasons.append(
                f"similarité sémantique élevée ({(agent.similarity or 0) * 100:.0f}%)"
            )
        if agent.category in query.required_category_values:
            reasons.append(f"catégorie {agent.category} requise")
        if dependency_tokens and (agent.integrations or []):
            if any(
                tok in (intg or "").lower() or (intg or "").lower() in tok
                for intg in agent.integrations or []
                for tok in dependency_tokens
            ):
                reasons.append("compatible avec la chaîne d'étapes parentes")
        uc_matches = sum(1 for uc in agent.use_cases if uc.lower() in all_text)
        if uc_matches > 0:
            reasons.append(f"{uc_matches} use case(s) correspondent")
        bf_matches = sum(1 for bf in (agent.best_for or []) if bf.lower() in all_text)
        if bf_matches > 0:
            reasons.append("optimisé pour ce cas d'usage")

        relevance_reason = (
            " · ".join(reasons) if reasons else f"RRF rank vectoriel #{rank_v}, métier #{rank_b}"
        )

        results.append(
            ScoredAgent(
                id=agent.id,
                name=agent.name,
                category=agent.category,
                description=agent.description,
                price_from=agent.price_from,
                score=agent.score,
                roi_score=agent.roi_score,
                use_cases=agent.use_cases,
                compatible_with=agent.compatible_with,
                best_for=agent.best_for,
                integrations=agent.integrations,
                website_domain=agent.website_domain,
                setup_difficulty=agent.setup_difficulty or "easy",
                time_to_value=agent.time_to_value,
                similarity=agent.similarity or 0,
                relevance_score=relevance_score,
                relevance_reason=relevance_reason,
            )
        )

    results.sort(key=lambda a: a.relevance_score, reverse=True)
    return results[:15]
