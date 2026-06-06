"""Validation programmatique post-sélection LLM — budget, redondance, taille minimale."""

from __future__ import annotations

from app.core.constants import DIFFICULTY_ALLOWED
from app.core.models import ScoredAgent
from app.domain.redundancy import REDUNDANT_TOOL_GROUPS, remove_redundant_by_groups

# Plancher produit (aligné tests Phase 0 / TS)
ABSOLUTE_MIN_AGENTS = 3


def redundancy_group_key(name: str) -> str | None:
    lower = name.lower().strip()
    for i, group in enumerate(REDUNDANT_TOOL_GROUPS):
        for token in group:
            t = token.lower()
            if lower == t or lower.startswith(t + " ") or t in lower:
                return f"g{i}"
    return None


def stack_total_cost(tools: list[ScoredAgent]) -> float:
    return sum(t.price_from or 0 for t in tools)


def filter_candidates_for_tech_level(
    candidates: list[ScoredAgent],
    tech_level: str,
) -> list[ScoredAgent]:
    """Si beginner, exclut les outils setup_difficulty=hard (règle stackBuilder TS)."""
    allowed = {d.lower() for d in DIFFICULTY_ALLOWED.get(tech_level, ["easy", "medium", "hard"])}
    filtered = [
        c for c in candidates if (c.setup_difficulty or "easy").lower() in allowed
    ]
    return filtered if filtered else candidates


def _swap_expensive_for_cheaper(
    selected: list[ScoredAgent],
    candidates: list[ScoredAgent],
    budget_max: int,
) -> list[ScoredAgent]:
    """Remplace un outil cher par un candidat moins cher (même pile, budget respecté)."""
    current = list(selected)
    used = {t.id for t in current}
    pool = sorted(
        [a for a in candidates if a.id not in used],
        key=lambda a: (a.price_from or 0, -a.relevance_score),
    )
    if not pool:
        return current

    improved = True
    while improved and stack_total_cost(current) > budget_max:
        improved = False
        expensive = sorted(current, key=lambda t: t.price_from or 0, reverse=True)
        for costly in expensive:
            for cheap in pool:
                if cheap.id in {t.id for t in current}:
                    continue
                trial = remove_redundant_by_groups(
                    [t for t in current if t.id != costly.id] + [cheap]
                )
                if len(trial) < len(current) - 1:
                    continue
                if stack_total_cost(trial) >= stack_total_cost(current):
                    continue
                if stack_total_cost(trial) <= budget_max:
                    current = trial
                    used = {t.id for t in current}
                    pool = [a for a in pool if a.id not in used]
                    improved = True
                    break
            if improved:
                break
    return current


def trim_to_budget(
    tools: list[ScoredAgent],
    budget_max: int,
    min_tools: int,
    candidates: list[ScoredAgent] | None = None,
) -> tuple[list[ScoredAgent], list[str]]:
    """
    Respecte le budget :
    1. Retire les plus chers tant que len > min_tools
    2. Tente des remplacements moins chers depuis les candidats
    3. Plancher ABSOLUTE_MIN_AGENTS si le budget l'exige encore
    """
    selected = list(tools)
    warnings: list[str] = []
    floor = max(ABSOLUTE_MIN_AGENTS, min(min_tools, ABSOLUTE_MIN_AGENTS))
    # floor = max(3, min(min_tools, 3)) = 3 always when min_tools >= 3

    total = stack_total_cost(selected)
    while total > budget_max and len(selected) > min_tools:
        worst = max(selected, key=lambda t: t.price_from or 0)
        selected = [t for t in selected if t.id != worst.id]
        total = stack_total_cost(selected)
        warnings.append(f"{worst.name} retiré (budget)")

    if candidates and total > budget_max:
        swapped = _swap_expensive_for_cheaper(selected, candidates, budget_max)
        if stack_total_cost(swapped) < total:
            selected = swapped
            total = stack_total_cost(selected)
            warnings.append("Remplacement par outils moins chers (budget)")

    while total > budget_max and len(selected) > ABSOLUTE_MIN_AGENTS:
        worst = max(selected, key=lambda t: t.price_from or 0)
        selected = [t for t in selected if t.id != worst.id]
        total = stack_total_cost(selected)
        warnings.append(f"{worst.name} retiré (budget strict, < min_tools)")

    if total > budget_max:
        warnings.append(
            f"Coût {total}€ encore > {budget_max}€ avec {len(selected)} outil(s)"
        )

    return selected, warnings


def refill_after_redundancy(
    tools: list[ScoredAgent],
    candidates: list[ScoredAgent],
    *,
    min_tools: int,
    max_tools: int,
    budget_max: int,
) -> tuple[list[ScoredAgent], list[str]]:
    """
    Après anti-redondance, réinjecte des candidats de groupes fonctionnels distincts
    jusqu'à atteindre min_tools (sans dépasser budget ni max_tools).
    """
    current = list(tools)
    warnings: list[str] = []
    pool = sorted(candidates, key=lambda a: a.relevance_score, reverse=True)
    used_ids = {t.id for t in current}

    while len(current) < min_tools and len(current) < max_tools:
        improved = False
        for agent in pool:
            if agent.id in used_ids:
                continue
            trial = remove_redundant_by_groups(current + [agent])
            if len(trial) <= len(current):
                continue
            if len(trial) > max_tools:
                continue
            if stack_total_cost(trial) > budget_max:
                continue
            current = trial
            used_ids = {t.id for t in current}
            improved = True
            break
        if not improved:
            break

    if len(current) < min_tools:
        warnings.append(
            f"Impossible d'atteindre {min_tools} outils distincts sous {budget_max}€"
        )
    elif len(tools) < len(current):
        warnings.append("Agents ajoutés après anti-redondance pour couvrir le minimum")

    return current, warnings
