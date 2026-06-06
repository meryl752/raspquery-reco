"""
Query analyzer — LLM structured (Cerebras → Groq) ; fallback heuristique désactivé par défaut.
"""

from __future__ import annotations

import asyncio
import logging
import sys

from app.core.config import Settings, get_settings
from app.core.constants import BUDGET_MAP
from app.core.models import UserContext
from app.domain.analyzed_query import (
    AnalyzedQuery,
    AtomicSubtask,
    FunctionalDomain,
    QueryAnalyzerPass1Output,
    QueryAnalyzerPass2Output,
)
from app.domain.query_fallback import build_bulletproof_fallback
from app.infra.llm import LlmClient, LlmNotConfiguredError, create_llm_client
from app.pipeline.errors import QueryAnalyzerUnavailableError

logger = logging.getLogger(__name__)

PASS1_MAX_TOKENS = 1200
PASS2_MAX_TOKENS = 600
PASS2_MIN_SUBTASKS = 5
PASS1_RETRY_DELAY_S = 1.5


def _group_domains_by_category(all_tasks: list[AtomicSubtask]) -> list[FunctionalDomain]:
    """Pass2 déterministe si le LLM ne renvoie pas de task_ids."""
    by_cat: dict[str, list[AtomicSubtask]] = {}
    for st in all_tasks:
        key = st.required_category.value
        by_cat.setdefault(key, []).append(st)
    return [
        FunctionalDomain(name=cat.replace("_", " ").title(), priority=i + 1, subtasks=sts)
        for i, (cat, sts) in enumerate(by_cat.items())
    ]


def _pass1_prompt(ctx: UserContext, budget_max: int) -> str:
    categories = AnalyzedQuery.category_list_for_prompt()
    locale = ctx.locale
    lang = (
        "Réponds en français pour tous les champs en langage naturel."
        if locale == "fr"
        else "Respond in English for all natural-language fields."
    )
    return f"""Tu es un expert en automatisation IA. Décompose l'objectif en sous-tâches atomiques.
{lang}

OBJECTIF: "{ctx.objective}"
SECTEUR: {ctx.sector} | BUDGET MAX: {budget_max}€/mois | NIVEAU: {ctx.tech_level}

Règles:
1. Chaque sous-tâche : id unique (t1, t2…), action précise et vérifiable (pas de vague « améliorer X »)
2. required_category parmi [{categories}]
3. depends_on = ids des tâches à finir AVANT ([] si aucune)
4. Dépendances logiques obligatoires (ex: capture leads → puis emailing)
5. Couvre tout l'objectif avec au moins 8 sous-tâches si l'objectif est ambitieux"""


def _pass2_prompt(subtasks: list[AtomicSubtask]) -> str:
    lines = "\n".join(f'- {s.id}: "{s.action[:100]}"' for s in subtasks)
    id_list = ", ".join(s.id for s in subtasks)
    return f"""Regroupe ces sous-tâches en domaines fonctionnels logiques.

IDS EXISTANTS (à réutiliser tels quels dans task_ids): {id_list}

SOUS-TÂCHES:
{lines}

JSON avec clés: domains[].name, domains[].priority, domains[].task_ids (liste d'ids, ex: ["t1","t2"])
Chaque id ne doit apparaître que dans un seul domaine. Priorité 1 = le plus important."""


def _use_heuristic_fallback(settings: Settings) -> bool:
    return settings.reco_dry_run or settings.reco_allow_heuristic_fallback


async def _pass1_with_retries(
    llm: LlmClient,
    ctx: UserContext,
    budget_max: int,
    settings: Settings,
) -> QueryAnalyzerPass1Output:
    last_exc: Exception | None = None
    attempts = max(1, settings.reco_llm_pass1_attempts)
    for attempt in range(attempts):
        try:
            return await llm.complete_structured(
                QueryAnalyzerPass1Output,
                _pass1_prompt(ctx, budget_max),
                system_prompt=(
                    "Tu es un analyseur de besoins produit. "
                    "Réponds uniquement avec le JSON structuré demandé."
                ),
                max_tokens=PASS1_MAX_TOKENS,
                schema_name="query_analyzer_pass1",
                preferred_model=ctx.preferred_model,
            )
        except Exception as exc:
            last_exc = exc
            if attempt < attempts - 1:
                logger.warning(
                    "query_analyzer: passe 1 tentative %d/%d (%s) — nouvel essai",
                    attempt + 1,
                    attempts,
                    exc,
                )
                await asyncio.sleep(PASS1_RETRY_DELAY_S * (attempt + 1))
    assert last_exc is not None
    raise last_exc


async def analyze_query(
    ctx: UserContext,
    llm: LlmClient | None = None,
    settings: Settings | None = None,
) -> AnalyzedQuery:
    """
    Analyse l'objectif via LLM (qualité nominale).
    Par défaut (RECO_ALLOW_HEURISTIC_FALLBACK=false) : échec explicite si tous les providers échouent.
    """
    _settings = settings or get_settings()
    budget_max = BUDGET_MAP.get(ctx.budget, 0)
    allow_fallback = _use_heuristic_fallback(_settings)

    if llm is None:
        llm = create_llm_client(_settings)

    if _settings.reco_dry_run and llm is None:
        return build_bulletproof_fallback(ctx.objective, ctx.sector, budget_max)

    if llm is None:
        msg = (
            "query_analyzer: aucun LLM configuré (CEREBRAS_API_KEY ou GROQ_API_KEY dans .env)"
        )
        if allow_fallback:
            logger.warning("%s — fallback heuristique", msg)
            print(f"⚠️  {msg} — fallback heuristique", file=sys.stderr)
            return build_bulletproof_fallback(ctx.objective, ctx.sector, budget_max)
        raise QueryAnalyzerUnavailableError(msg)

    try:
        pass1 = await _pass1_with_retries(llm, ctx, budget_max, _settings)
    except (LlmNotConfiguredError, Exception) as exc:
        msg = f"query_analyzer: passe 1 LLM échouée après retries ({exc})"
        if allow_fallback:
            logger.warning("%s — fallback heuristique", msg)
            print(f"⚠️  {msg} — fallback heuristique", file=sys.stderr)
            return build_bulletproof_fallback(ctx.objective, ctx.sector, budget_max)
        raise QueryAnalyzerUnavailableError(msg) from exc

    try:
        result = pass1.to_analyzed_query(ctx.objective, budget_max)
    except ValueError as exc:
        msg = f"query_analyzer: AnalyzedQuery invalide ({exc})"
        if allow_fallback:
            logger.warning("%s — fallback heuristique", msg)
            return build_bulletproof_fallback(ctx.objective, ctx.sector, budget_max)
        raise QueryAnalyzerUnavailableError(msg) from exc

    all_tasks = [st for domain in result.domains for st in domain.subtasks]
    if len(all_tasks) >= PASS2_MIN_SUBTASKS:
        step_delay = max(0, _settings.reco_llm_step_delay_ms) / 1000.0
        if step_delay > 0 and llm:
            await asyncio.sleep(step_delay)
        task_ids = [st.id for st in all_tasks]
        try:
            pass2 = await llm.complete_structured(
                QueryAnalyzerPass2Output,
                _pass2_prompt(all_tasks),
                system_prompt=(
                    "Regroupe les tâches en domaines. JSON uniquement. "
                    "Champ obligatoire: task_ids avec les ids fournis (t1, t2, …)."
                ),
                max_tokens=PASS2_MAX_TOKENS,
                schema_name="query_analyzer_pass2",
                preferred_model=ctx.preferred_model,
                known_task_ids=task_ids,
            )
            by_id = {st.id: st for st in all_tasks}
            grouped = pass2.apply_to(result, by_id)
            if len(grouped.domains) > 1:
                result = grouped
                logger.info("query_analyzer: pass2 LLM — %d domaines", len(result.domains))
            else:
                raise ValueError("pass2 LLM n'a produit aucun regroupement")
        except Exception as exc:
            logger.info(
                "query_analyzer: pass2 LLM optionnelle (%s) — regroupement par catégorie",
                exc,
            )
            result = AnalyzedQuery(
                original=result.original,
                domains=_group_domains_by_category(all_tasks),
                implicit_constraints=result.implicit_constraints,
                sector_context=result.sector_context,
                budget_max=result.budget_max,
            )

    assert result.required_categories
    logger.info(
        "query_analyzer: %d sous-tâches, catégories=%s",
        len(result.subtasks),
        result.required_category_values,
    )
    return result
