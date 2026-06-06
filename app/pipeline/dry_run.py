"""Fixture minimale pour tester le contrat HTTP sans Supabase ni LLM."""

from app.core.models import (
    FinalStack,
    OrchestratorMeta,
    OrchestratorResult,
    StackAgent,
    SubTask,
    UserContext,
    VectorAgent,
)
from app.domain.analyzed_query import (
    AnalyzedQuery,
    AtomicSubtask,
    FunctionalDomain,
    ValidCategory,
)


def dry_run_analyzed_query(ctx: UserContext) -> AnalyzedQuery:
    return AnalyzedQuery(
        original=ctx.objective,
        domains=[
            FunctionalDomain(
                name="core",
                priority=1,
                subtasks=[
                    AtomicSubtask(
                        id="d1_t1",
                        action=ctx.objective[:120],
                        required_category=ValidCategory.AUTOMATION,
                        depends_on=[],
                        can_be_automated=True,
                    )
                ],
            )
        ],
        implicit_constraints=[],
        sector_context=ctx.sector,
        budget_max=0,
    )


def dry_run_vector_agents() -> list[VectorAgent]:
    return [
        VectorAgent(
            id="00000000-0000-4000-8000-000000000001",
            name="Make",
            category="automation",
            description="Automatisation no-code",
            price_from=0,
            score=85,
            roi_score=80,
            use_cases=["automation", "workflows"],
            compatible_with=[],
            similarity=0.82,
            setup_difficulty="easy",
            time_to_value="1 jour",
        ),
        VectorAgent(
            id="00000000-0000-4000-8000-000000000002",
            name="Notion AI",
            category="copywriting",
            description="Docs et contenu assistés par IA",
            price_from=10,
            score=78,
            roi_score=75,
            use_cases=["content", "documentation"],
            compatible_with=[],
            similarity=0.71,
            setup_difficulty="easy",
        ),
    ]


def dry_run_final_stack(ctx: UserContext, agent_names: list[str]) -> FinalStack:
    agents = [
        StackAgent(
            id="00000000-0000-4000-8000-000000000001",
            name="Make",
            category="automation",
            price_from=0,
            score=85,
            rank=1,
            role="Orchestration",
            reason="[dry-run] Automatisation adaptée à l'objectif.",
            concrete_result="Flux automatisés sans code.",
        ),
        StackAgent(
            id="00000000-0000-4000-8000-000000000002",
            name="Notion AI",
            category="copywriting",
            price_from=10,
            score=78,
            rank=2,
            role="Contenu",
            reason="[dry-run] Rédaction et structure documentaire.",
            concrete_result="Briefs et docs générés plus vite.",
        ),
    ]
    return FinalStack(
        stack_name=f"Stack {ctx.sector} (dry-run)",
        justification="Réponse fixture — moteur Python non branché sur LLM.",
        total_cost=10,
        roi_estimate=120,
        time_saved_per_week=5,
        quick_wins=["Activer un scénario Make", "Créer un template Notion"],
        warnings=["Mode RECO_DRY_RUN=true — ne pas utiliser en production."],
        subtasks=[
            SubTask(
                name="Automatiser",
                without_ai="Tâches manuelles répétitives",
                with_ai="Scénarios Make",
                tool_name="Make",
            )
        ],
        agents=agents,
    )


def dry_run_result(ctx: UserContext, processing_ms: int) -> OrchestratorResult:
    query = dry_run_analyzed_query(ctx)
    return OrchestratorResult(
        stack=dry_run_final_stack(ctx, [a.name for a in dry_run_vector_agents()]),
        meta=OrchestratorMeta(
            agents_analyzed=len(dry_run_vector_agents()),
            agents_shortlisted=2,
            subtasks_detected=len(query.subtasks),
            processing_time_ms=processing_ms,
            retrieval_mode="fallback",
            embedding_latency_ms=0,
        ),
    )
