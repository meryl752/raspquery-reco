from app.core.models import ScoredAgent
from app.pipeline.stack_validation import redundancy_group_key


def fallback_selection_from_candidates(
    candidates: list[ScoredAgent],
    subtasks: list[str],
    min_tools: int,
    max_tools: int,
    budget_max: int,
) -> tuple[list[str], dict[str, str], list[str]]:
    """
    Sélection déterministe si le LLM échoue.
    Priorise un outil par groupe de redondance (évite 2 chatbots identiques).
    """
    sorted_c = sorted(candidates, key=lambda a: a.relevance_score, reverse=True)
    selected_ids: list[str] = []
    subtask_coverage: dict[str, str] = {}
    used_groups: set[str] = set()
    total_cost = 0.0

    def add_agent(agent: ScoredAgent, *, relax_budget: bool = False) -> bool:
        nonlocal total_cost
        if agent.id in selected_ids or len(selected_ids) >= max_tools:
            return False
        gk = redundancy_group_key(agent.name)
        if gk and gk in used_groups:
            return False
        price = agent.price_from or 0
        if (
            not relax_budget
            and total_cost + price > budget_max
            and len(selected_ids) >= min_tools
        ):
            return False
        selected_ids.append(agent.id)
        total_cost += price
        if gk:
            used_groups.add(gk)
        idx = len(selected_ids) - 1
        if idx < len(subtasks):
            subtask_coverage[subtasks[idx]] = agent.id
        return True

    for agent in sorted_c:
        if len(selected_ids) >= max_tools:
            break
        add_agent(agent)

    for agent in sorted_c:
        if len(selected_ids) >= max_tools:
            break
        gk = redundancy_group_key(agent.name)
        if gk and gk in used_groups:
            continue
        add_agent(agent)

    if len(selected_ids) < min_tools:
        for agent in sorted_c:
            if len(selected_ids) >= min_tools:
                break
            if agent.id in selected_ids:
                continue
            add_agent(agent, relax_budget=True)

    return (
        selected_ids,
        subtask_coverage,
        ["Sélection automatique (réponse LLM non parsable)"],
    )
