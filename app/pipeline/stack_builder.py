"""
Construction de stack — parité stackai/lib/agents/stackBuilder.ts
"""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from app.core.constants import BUDGET_MAP
from app.core.models import FinalStack, ScoredAgent, StackAgent, SubTask, UserContext
from app.domain.analyzed_query import AnalyzedQuery
from app.domain.redundancy import remove_redundant_by_groups
from app.infra.llm import LlmClient
from app.pipeline.fallbacks.enrichment import SelectedToolRow, build_fallback_enrichment
from app.pipeline.fallbacks.selection import fallback_selection_from_candidates
from app.pipeline.role_copy import (
    ToolLike,
    impact_level_from_roi,
    normalize_stack_agent_role,
    truncate_catalog_snippet,
)
from app.pipeline.stack_validation import (
    filter_candidates_for_tech_level,
    refill_after_redundancy,
    trim_to_budget,
)

logger = logging.getLogger(__name__)

TECH_MAP = {
    "beginner": "débutant (no-code)",
    "intermediate": "intermédiaire (no-code avancé)",
    "advanced": "avancé (code OK)",
}
TEAM_MAP = {
    "solo": "solo",
    "small": "petite équipe",
    "medium": "équipe moyenne",
    "large": "grande org",
}


class StackSelectionOutput(BaseModel):
    selected_ids: list[str] = Field(default_factory=list)
    subtask_coverage: dict[str, str] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class StackAgentEnrichment(BaseModel):
    id: str
    role: str = ""
    reason: str = ""
    concrete_result: str = ""


class StackEnrichmentOutput(BaseModel):
    stack_name: str = "Stack IA"
    justification: str = ""
    quick_wins: list[str] = Field(default_factory=list)
    agents: list[StackAgentEnrichment] = Field(default_factory=list)


def _format_candidates_for_selection(candidates: list[ScoredAgent]) -> str:
    blocks = []
    for i, a in enumerate(candidates, 1):
        use_cases = ", ".join((a.use_cases or [])[:5]) or "N/A"
        best_for = ", ".join((a.best_for or [])[:3]) or "N/A"
        diff = a.setup_difficulty or "easy"
        blocks.append(
            f'{i}. ID="{a.id}" | NOM="{a.name}" | PRIX={a.price_from}€ | '
            f"DIFF={diff} | SCORE={a.relevance_score}/100\n"
            f"   USE_CASES: {use_cases}\n"
            f"   BEST_FOR: {best_for}"
        )
    return "\n\n".join(blocks)


def _format_selected_for_enrichment(tools: list[SelectedToolRow]) -> str:
    blocks = []
    for t in tools:
        use_cases = ", ".join((t.use_cases or [])[:5]) or "N/A"
        best_for = ", ".join((t.best_for or [])[:3]) or "N/A"
        desc_hint = truncate_catalog_snippet(t.description)
        blocks.append(
            f'[RANK {t.rank}] ID="{t.id}" | NOM="{t.name}"\n'
            f'   SOUS-TÂCHE ASSIGNÉE: "{t.assigned_subtask}"\n'
            f"   USE_CASES (catalogue): {use_cases}\n"
            f"   BEST_FOR: {best_for}\n"
            f"   RÉSUMÉ CATALOGUE (ne pas recopier): {desc_hint}"
        )
    return "\n\n".join(blocks)


def _resolve_subtask_tool_id(
    subtask: str,
    subtask_coverage: dict[str, str],
    selected: list[SelectedToolRow],
) -> SelectedToolRow | None:
    tid = subtask_coverage.get(subtask)
    if tid:
        return next((t for t in selected if t.id == tid), None)
    needle = subtask.lower()[:20]
    for key, tool_id in subtask_coverage.items():
        kl = key.lower()
        if needle in kl or kl[:20] in subtask.lower():
            return next((t for t in selected if t.id == tool_id), None)
    return None


def _build_selection_prompt(
    ctx: UserContext,
    query: AnalyzedQuery,
    candidates: list[ScoredAgent],
    *,
    budget_max: int,
    min_tools: int,
    max_tools: int,
) -> str:
    current_tools = ", ".join(ctx.current_tools) if ctx.current_tools else "aucun"
    subtasks_block = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(query.subtasks))
    return f"""Tu sélectionnes les meilleurs outils IA depuis une liste de candidats.

CONTEXTE UTILISATEUR:
- Objectif: {query.original}
- Secteur: {ctx.sector}
- Budget MAX: {budget_max}€/mois
- Niveau technique: {ctx.tech_level}
- Outils existants: {current_tools}

SOUS-TÂCHES À COUVRIR:
{subtasks_block}

CANDIDATS (capacités réelles depuis notre base):
{_format_candidates_for_selection(candidates)}

RÈGLES:
1. Budget total des outils sélectionnés ≤ {budget_max}€/mois
2. 1 outil par sous-tâche — pas de doublons fonctionnels
3. Nombre d'outils: {min_tools}-{max_tools}
4. Respecte le niveau technique — si beginner, écarte les outils "hard"
5. Si une sous-tâche n'est couverte par aucun candidat, indique-le dans warnings

JSON UNIQUEMENT (pas de markdown, pas de texte avant/après):
{{
  "selected_ids": ["uuid1", "uuid2"],
  "subtask_coverage": {{"sous-tâche exacte 1": "uuid1", "sous-tâche exacte 2": "uuid2"}},
  "warnings": ["besoin non couvert: X"]
}}"""


def _build_enrichment_prompt(
    ctx: UserContext,
    query: AnalyzedQuery,
    selected_tools: list[SelectedToolRow],
) -> str:
    formatted = _format_selected_for_enrichment(selected_tools)
    tech = TECH_MAP.get(ctx.tech_level, ctx.tech_level)
    team = TEAM_MAP.get(ctx.team_size, ctx.team_size)

    if ctx.locale == "fr":
        return f"""Tu enrichis la présentation d'outils IA sélectionnés pour un utilisateur spécifique. Tout le texte utilisateur doit être en français.

UTILISATEUR:
- Objectif: {query.original}
- Secteur: {ctx.sector} | {query.sector_context}
- Profil: {tech} | {team}

OUTILS SÉLECTIONNÉS (données vérifiées depuis notre base):
{formatted}

Pour chaque outil, génère:
- "role": UNE phrase (max 18 mots) = ce que cet outil fait POUR L'OBJECTIF UTILISATEUR et la SOUS-TÂCHE ASSIGNÉE. Interdit de recopier RÉSUMÉ CATALOGUE ou USE_CASES tels quels.
- "reason": pourquoi cet outil pour CE profil (max 25 mots)
- "concrete_result": résultat concret sans chiffres inventés

Pour le stack global:
- "stack_name": nom court (max 4 mots)
- "justification": 2-3 phrases
- "quick_wins": 3 actions datées

JSON UNIQUEMENT:
{{
  "stack_name": "...",
  "justification": "...",
  "quick_wins": ["...", "...", "..."],
  "agents": [{{"id": "uuid", "role": "...", "reason": "...", "concrete_result": "..."}}]
}}"""

    return f"""You enrich AI tool presentations for a specific user. All user-facing text must be in English.

USER:
- Objective: {query.original}
- Sector: {ctx.sector} | {query.sector_context}
- Profile: {tech} | {team}

SELECTED TOOLS (verified from our database):
{formatted}

For each tool:
- "role": ONE sentence (max 18 words) = what this tool does FOR THE USER'S OBJECTIVE and ASSIGNED SUBTASK. Do NOT copy CATALOG SUMMARY or USE_CASES verbatim.
- "reason": why this tool for THIS profile (max 25 words)
- "concrete_result": concrete outcome, no invented numbers

For the stack:
- "stack_name": short memorable name (max 4 words)
- "justification": 2-3 sentences
- "quick_wins": 3 dated actions

JSON ONLY:
{{
  "stack_name": "...",
  "justification": "...",
  "quick_wins": ["...", "...", "..."],
  "agents": [{{"id": "uuid", "role": "...", "reason": "...", "concrete_result": "..."}}]
}}"""


def _assemble_stack(
    enrichment: StackEnrichmentOutput,
    selected: list[SelectedToolRow],
    query: AnalyzedQuery,
    ctx: UserContext,
    subtask_coverage: dict[str, str],
    warnings: list[str],
) -> FinalStack:
    by_id = {t.id: t for t in selected}
    llm_by_id = {a.id: a for a in enrichment.agents}
    locale = ctx.locale

    agents_out: list[StackAgent] = []
    for tool in selected:
        llm_a = llm_by_id.get(tool.id)
        tool_like = ToolLike(
            name=tool.name,
            description=tool.description,
            use_cases=tool.use_cases,
            best_for=tool.best_for,
            assigned_subtask=tool.assigned_subtask,
        )
        role = normalize_stack_agent_role(
            llm_a.role if llm_a else None,
            tool_like,
            query.original,
            locale,
        )
        qualitative = (
            (llm_a.concrete_result if llm_a and llm_a.concrete_result else None)
            or (tool.use_cases[0] if tool.use_cases else "Automatisation")
        )
        impact = impact_level_from_roi(tool.roi_score, locale)
        concrete = f"{qualitative} — Impact estimé : {impact}"

        agents_out.append(
            StackAgent(
                id=tool.id,
                name=tool.name,
                category=tool.category,
                price_from=tool.price_from,
                score=float(tool.relevance_score),
                rank=tool.rank,
                role=role,
                reason=(llm_a.reason if llm_a and llm_a.reason else tool.relevance_reason)[
                    :200
                ],
                concrete_result=concrete[:300],
                website_domain=tool.website_domain,
                setup_difficulty=tool.setup_difficulty,
                time_to_value=tool.time_to_value,
            )
        )

    subtasks_out: list[SubTask] = []
    for st in query.subtasks:
        row = _resolve_subtask_tool_id(st, subtask_coverage, selected)
        subtasks_out.append(
            SubTask(
                name=st,
                without_ai="Processus manuel",
                with_ai=f"Automatisé via {row.name}" if row else "Non couvert",
                tool_name=row.name if row else "N/A",
            )
        )

    for st in subtasks_out:
        if st.tool_name == "N/A":
            snippet = st.name[:20]
            if not any(snippet in w for w in warnings):
                warnings.append(f'Besoin non couvert: "{st.name}". Aucun outil correspondant.')

    total = sum(a.price_from for a in agents_out)
    avg_roi = (
        round(sum(t.roi_score for t in selected) / len(selected)) if selected else 50
    )

    return FinalStack(
        stack_name=enrichment.stack_name or (
            "Stack IA Recommandé" if locale == "fr" else "Recommended AI Stack"
        ),
        justification=enrichment.justification,
        total_cost=total,
        roi_estimate=float(avg_roi),
        time_saved_per_week=round(avg_roi / 10),
        quick_wins=enrichment.quick_wins[:5],
        warnings=warnings,
        subtasks=subtasks_out,
        agents=agents_out,
    )


async def build_stack(
    ctx: UserContext,
    query: AnalyzedQuery,
    candidates: list[ScoredAgent],
    llm: LlmClient | None = None,
) -> FinalStack | None:
    if not candidates:
        return None

    candidates = filter_candidates_for_tech_level(candidates, ctx.tech_level)
    subtask_count = len(query.subtasks)
    min_tools = max(3, min(subtask_count, 4))
    max_tools = min(8, max(subtask_count + 1, 4))
    budget_max = BUDGET_MAP.get(ctx.budget, 0)

    pool = sorted(candidates, key=lambda a: a.relevance_score, reverse=True)[:15]

    selected_ids: list[str] = []
    subtask_coverage: dict[str, str] = {}
    selection_warnings: list[str] = []

    selection_prompt = _build_selection_prompt(
        ctx,
        query,
        pool,
        budget_max=budget_max,
        min_tools=min_tools,
        max_tools=max_tools,
    )

    if llm:
        try:
            sel = await llm.complete_structured(
                StackSelectionOutput,
                selection_prompt,
                system_prompt=(
                    "Sélection d'outils. JSON uniquement. Clé selected_ids obligatoire."
                ),
                max_tokens=800,
                schema_name="stack_selection",
                prefer_json_object=True,
                preferred_model=ctx.preferred_model,
            )
            if sel.selected_ids:
                selected_ids = sel.selected_ids
                subtask_coverage = sel.subtask_coverage
                selection_warnings = list(sel.warnings)
                logger.info(
                    "stack_builder: sélection LLM — %d outils", len(selected_ids)
                )
        except Exception as exc:
            logger.warning("stack_builder sélection LLM (%s) — fallback", exc)

    if not selected_ids:
        selected_ids, subtask_coverage, fb_warn = fallback_selection_from_candidates(
            pool, query.subtasks, min_tools, max_tools, budget_max
        )
        selection_warnings.extend(fb_warn)

    valid_ids = [i for i in selected_ids if any(c.id == i for c in pool)]
    if len(valid_ids) != len(selected_ids):
        selection_warnings.append(
            f"{len(selected_ids) - len(valid_ids)} ID(s) invalide(s) supprimé(s)"
        )
    if not valid_ids:
        return None

    selected_tools: list[ScoredAgent] = [
        next(x for x in pool if x.id == vid) for vid in valid_ids
    ]

    selected_tools, budget_warnings = trim_to_budget(
        selected_tools, budget_max, min_tools, pool
    )
    selection_warnings.extend(budget_warnings)

    before = len(selected_tools)
    selected_tools = remove_redundant_by_groups(selected_tools)
    if len(selected_tools) < before:
        selection_warnings.append("Outils redondants retirés (groupes fonctionnels)")

    selected_tools, refill_warnings = refill_after_redundancy(
        selected_tools,
        pool,
        min_tools=min_tools,
        max_tools=max_tools,
        budget_max=budget_max,
    )
    selection_warnings.extend(refill_warnings)

    selected_tools, budget_warnings2 = trim_to_budget(
        selected_tools, budget_max, min_tools, pool
    )
    selection_warnings.extend(budget_warnings2)

    if not selected_tools:
        return None

    selected_rows: list[SelectedToolRow] = []
    for index, agent in enumerate(selected_tools):
        assigned = next(
            (k for k, vid in subtask_coverage.items() if vid == agent.id),
            None,
        )
        if not assigned:
            assigned = query.subtasks[index] if index < len(query.subtasks) else ""
        selected_rows.append(
            SelectedToolRow.from_scored(
                agent, rank=index + 1, assigned_subtask=assigned or ""
            )
        )

    # Re-rank après filtrage
    selected_rows = [
        SelectedToolRow.from_scored(
            next(x for x in pool if x.id == row.id),
            rank=i + 1,
            assigned_subtask=row.assigned_subtask,
        )
        for i, row in enumerate(selected_rows)
    ]

    enrichment_data = build_fallback_enrichment(selected_rows, query, ctx)
    enrichment = StackEnrichmentOutput(
        stack_name=str(enrichment_data.get("stack_name", "")),
        justification=str(enrichment_data.get("justification", "")),
        quick_wins=list(enrichment_data.get("quick_wins") or []),
        agents=[
            StackAgentEnrichment.model_validate(a)
            for a in (enrichment_data.get("agents") or [])
        ],
    )

    if llm:
        enrich_prompt = _build_enrichment_prompt(ctx, query, selected_rows)
        sys = (
            "Texte utilisateur en français. JSON uniquement."
            if ctx.locale == "fr"
            else "User-facing text in English. JSON only."
        )
        try:
            enrichment = await llm.complete_structured(
                StackEnrichmentOutput,
                enrich_prompt,
                system_prompt=sys,
                max_tokens=2000,
                schema_name="stack_enrichment",
                preferred_model=ctx.preferred_model,
            )
            logger.info('stack_builder: enrichissement LLM — "%s"', enrichment.stack_name)
        except Exception as exc:
            logger.warning(
                "stack_builder enrichissement LLM (%s) — fallback catalogue", exc
            )

    stack = _assemble_stack(
        enrichment,
        selected_rows,
        query,
        ctx,
        subtask_coverage,
        selection_warnings,
    )
    logger.info(
        'stack_builder: stack final "%s" — %d agents, %s€/mois',
        stack.stack_name,
        len(stack.agents),
        stack.total_cost,
    )
    return stack
