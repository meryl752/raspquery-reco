"""Enrichissement déterministe — aligné stackai/lib/agents/enrichmentFallback.ts."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.models import ScoredAgent, UserContext
from app.domain.analyzed_query import AnalyzedQuery
from app.pipeline.role_copy import ToolLike, build_deterministic_role


@dataclass
class SelectedToolRow:
    """Outil sélectionné + sous-tâche assignée (comme le TS)."""

    id: str
    name: str
    category: str
    description: str
    price_from: float
    relevance_score: int
    relevance_reason: str
    use_cases: list[str]
    best_for: list[str] | None
    roi_score: float
    website_domain: str | None
    setup_difficulty: str | None
    time_to_value: str | None
    rank: int
    assigned_subtask: str

    @classmethod
    def from_scored(
        cls,
        agent: ScoredAgent,
        *,
        rank: int,
        assigned_subtask: str,
    ) -> SelectedToolRow:
        return cls(
            id=agent.id,
            name=agent.name,
            category=agent.category,
            description=agent.description,
            price_from=agent.price_from,
            relevance_score=agent.relevance_score,
            relevance_reason=agent.relevance_reason,
            use_cases=agent.use_cases,
            best_for=agent.best_for,
            roi_score=agent.roi_score,
            website_domain=agent.website_domain,
            setup_difficulty=agent.setup_difficulty,
            time_to_value=agent.time_to_value,
            rank=rank,
            assigned_subtask=assigned_subtask,
        )


def build_fallback_enrichment(
    selected_tools: list[SelectedToolRow],
    query: AnalyzedQuery,
    ctx: UserContext,
) -> dict:
    is_fr = ctx.locale != "en"
    objective_snippet = query.original.strip()[:140]
    ellipsis = "…" if len(query.original.strip()) > 140 else ""

    return {
        "stack_name": "Stack recommandé" if is_fr else "Recommended stack",
        "justification": (
            f"Stack construit pour : {objective_snippet}{ellipsis}. "
            "Les textes détaillés seront affinés lors d'une prochaine génération."
            if is_fr
            else f"Stack built for: {objective_snippet}{ellipsis}. "
            "Detailed copy may be refined on a future generation."
        ),
        "quick_wins": (
            [
                "Semaine 1 : connecter le premier outil à votre workflow",
                "Semaine 2 : automatiser une sous-tâche prioritaire",
                "Semaine 3 : mesurer le temps gagné et ajuster",
            ]
            if is_fr
            else [
                "Week 1: connect the first tool to your workflow",
                "Week 2: automate one priority subtask",
                "Week 3: measure time saved and adjust",
            ]
        ),
        "agents": [
            {
                "id": tool.id,
                "role": build_deterministic_role(
                    ToolLike(
                        name=tool.name,
                        use_cases=tool.use_cases,
                        assigned_subtask=tool.assigned_subtask,
                    ),
                    query.original,
                    ctx.locale,
                ),
                "reason": tool.relevance_reason
                or (
                    f"Pertinent pour {ctx.sector} (score catalogue {tool.relevance_score}/100)."
                    if is_fr
                    else f"Relevant for {ctx.sector} (catalog score {tool.relevance_score}/100)."
                ),
                "concrete_result": (
                    f"{(tool.use_cases or ['Automatisation'])[0]} pour votre projet"
                    if is_fr
                    else f"{(tool.use_cases or ['Automation'])[0]} for your project"
                ),
            }
            for tool in selected_tools
        ],
    }
