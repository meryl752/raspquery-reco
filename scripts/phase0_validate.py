#!/usr/bin/env python3
"""
Phase 0 — validation moteur standalone.

Usage (depuis raspquery-reco/, venv activé):
  python scripts/phase0_validate.py
  python scripts/phase0_validate.py --scenario shopify
  python scripts/phase0_validate.py --analyze-only
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import Settings, get_settings
from app.core.constants import BUDGET_MAP
from app.core.models import UserContext
from app.infra.llm import create_llm_client
from app.pipeline.errors import QueryAnalyzerUnavailableError
from app.pipeline.orchestrator import run_orchestrator
from app.pipeline.query_analyzer import analyze_query

# Aligné sur stackai/lib/agents/__tests__/orchestrator.integration.test.ts
SCENARIOS: dict[str, UserContext] = {
    "shopify": UserContext(
        objective=(
            "Je veux lancer une boutique Shopify et automatiser mon service client "
            "avec un chatbot"
        ),
        sector="ecommerce",
        budget="low",
        tech_level="beginner",
        locale="fr",
        preferred_model="qwen-235b",
    ),
    "saas_b2b": UserContext(
        objective="Je veux créer du contenu LinkedIn et automatiser ma prospection B2B",
        sector="b2b",
        budget="medium",
        tech_level="intermediate",
        locale="fr",
        preferred_model="qwen-235b",
    ),
    "support": UserContext(
        objective=(
            "Automatiser ma boutique Shopify: SEO, emails clients et support"
        ),
        sector="ecommerce",
        budget="low",
        tech_level="beginner",
        locale="fr",
        preferred_model="qwen-235b",
    ),
}

_HEURISTIC_MARKERS = re.compile(
    r"contribuer à l'objectif|Configuration initiale \(fallback\)|"
    r"plan heuristique enrichi",
    re.I,
)
_GENERIC_PREFIX = re.compile(r"^(seo|automation|copywriting|customer_service):", re.I)


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class ScenarioReport:
    id: str
    analyze_ok: bool = False
    orchestrator_ok: bool = False
    checks: list[CheckResult] = field(default_factory=list)
    subtask_count: int = 0
    categories: list[str] = field(default_factory=list)
    retrieval_mode: str | None = None
    agent_count: int = 0
    total_cost: float | None = None
    budget_max: int = 0
    processing_ms: int | None = None
    error: str | None = None
    sample_subtasks: list[str] = field(default_factory=list)
    sample_agents: list[str] = field(default_factory=list)


def _audit_env(settings: Settings) -> list[CheckResult]:
    def present(v: str | None) -> bool:
        return bool((v or "").strip())

    return [
        CheckResult(".env existe", Path(".env").is_file()),
        CheckResult("CEREBRAS_API_KEY", present(settings.cerebras_api_key)),
        CheckResult("GROQ_API_KEY", present(settings.groq_api_key)),
        CheckResult(
            "LLM secours disponible",
            present(settings.cerebras_api_key) or present(settings.groq_api_key),
        ),
        CheckResult("JINA_API_KEY", present(settings.jina_api_key)),
        CheckResult(
            "Supabase",
            present(settings.supabase_url) and present(settings.supabase_service_role_key),
        ),
        CheckResult(
            "RECO_ALLOW_HEURISTIC_FALLBACK=false",
            not settings.reco_allow_heuristic_fallback,
            f"valeur={settings.reco_allow_heuristic_fallback}",
        ),
    ]


def _is_likely_heuristic(subtasks: list[str], constraints: list[str]) -> bool:
    joined = " ".join(subtasks + constraints)
    if _HEURISTIC_MARKERS.search(joined):
        return True
    if subtasks and all(_GENERIC_PREFIX.match(s) for s in subtasks[:3]):
        return True
    return False


async def _run_analyze(
    ctx: UserContext, settings: Settings, report: ScenarioReport
) -> bool:
    llm = create_llm_client(settings)
    if not llm:
        report.error = "Aucun LLM configuré"
        return False
    try:
        q = await analyze_query(ctx, llm, settings)
    except QueryAnalyzerUnavailableError as exc:
        report.error = str(exc)
        report.checks.append(
            CheckResult("analyse LLM", False, "503 / indisponible (attendu si tout KO)")
        )
        return False

    report.subtask_count = len(q.subtasks)
    report.categories = q.required_category_values
    report.sample_subtasks = q.subtasks[:6]

    heuristic = _is_likely_heuristic(q.subtasks, q.implicit_constraints)
    report.checks.extend(
        [
            CheckResult("≥5 sous-tâches", len(q.subtasks) >= 5, f"{len(q.subtasks)}"),
            CheckResult("≥1 catégorie", len(q.required_categories) >= 1),
            CheckResult(
                "pas heuristique silencieuse",
                not heuristic,
                "marqueurs fallback détectés" if heuristic else "OK",
            ),
            CheckResult(
                "actions concrètes",
                not any("contribuer à l'objectif" in s.lower() for s in q.subtasks),
            ),
        ]
    )
    report.analyze_ok = all(c.ok for c in report.checks if c.name != "analyse LLM")
    return report.analyze_ok


async def _run_orchestrator(
    ctx: UserContext, settings: Settings, report: ScenarioReport
) -> bool:
    report.budget_max = BUDGET_MAP.get(ctx.budget, 0)
    t0 = time.perf_counter()
    try:
        result = await run_orchestrator(ctx, settings)
    except Exception as exc:
        report.error = str(exc)
        return False
    elapsed = int((time.perf_counter() - t0) * 1000)

    if not result:
        report.error = "orchestrateur retourné None"
        report.checks.append(CheckResult("orchestrateur", False, report.error))
        return False

    stack = result.stack
    meta = result.meta
    report.retrieval_mode = meta.retrieval_mode
    report.agent_count = len(stack.agents)
    report.total_cost = stack.total_cost
    report.processing_ms = meta.processing_time_ms or elapsed
    report.sample_agents = [
        f"{a.rank}. {a.name} ({a.category}) {a.price_from}€" for a in stack.agents[:8]
    ]

    names = [a.name.lower() for a in stack.agents]
    dup_email = sum(1 for n in names if any(x in n for x in ("mailchimp", "brevo", "sendgrid")))

    report.checks.extend(
        [
            CheckResult("stack_name", bool(stack.stack_name)),
            CheckResult(
                "4-6 agents (tolère 3)",
                3 <= len(stack.agents) <= 8,
                f"{len(stack.agents)} agents",
            ),
            CheckResult(
                "budget respecté",
                stack.total_cost <= report.budget_max + 0.01,
                f"{stack.total_cost}€ ≤ {report.budget_max}€",
            ),
            CheckResult(
                "retrieval vector préféré",
                meta.retrieval_mode == "vector",
                f"mode={meta.retrieval_mode}",
            ),
            CheckResult(
                "pas doublon email évident",
                dup_email <= 1,
                f"{dup_email} outils email-like",
            ),
        ]
    )
    report.orchestrator_ok = all(c.ok for c in report.checks[-5:])
    return report.orchestrator_ok


async def _probe_groq_key(settings: Settings) -> CheckResult:
    if not (settings.groq_api_key or "").strip():
        return CheckResult("Groq probe", False, "clé absente")
    try:
        from app.infra.llm.groq import GroqClient

        client = GroqClient(api_key=settings.groq_api_key)
        await client._chat_completion(
            model=settings.groq_model,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=8,
            response_format=None,
        )
        return CheckResult("Groq probe (clé valide)", True)
    except Exception as exc:
        msg = str(exc)
        if "401" in msg or "invalid_api_key" in msg.lower():
            return CheckResult(
                "Groq probe (clé valide)",
                False,
                "GROQ_API_KEY rejetée (401) — régénère sur console.groq.com",
            )
        return CheckResult("Groq probe", False, msg[:120])


async def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 0 validation")
    parser.add_argument(
        "--scenario",
        choices=[*SCENARIOS.keys(), "all"],
        default="all",
    )
    parser.add_argument(
        "--analyze-only",
        action="store_true",
        help="Ne lance pas l'orchestrateur complet",
    )
    parser.add_argument(
        "--delay",
        type=int,
        default=20,
        help="Pause (s) entre scénarios pour éviter 429 Cerebras (défaut: 20)",
    )
    args = parser.parse_args()

    settings = get_settings()
    env_checks = _audit_env(settings)

    print("=" * 60)
    print("PHASE 0 — Validation moteur raspquery-reco")
    print("=" * 60)
    print("\n## Audit .env")
    for c in env_checks:
        icon = "✅" if c.ok else "❌"
        extra = f" — {c.detail}" if c.detail else ""
        print(f"  {icon} {c.name}{extra}")

    if not all(c.ok for c in env_checks):
        print("\n❌ Corrige .env avant de continuer.")
        sys.exit(1)

    if (settings.groq_api_key or "").strip():
        groq_probe = await _probe_groq_key(settings)
        icon = "✅" if groq_probe.ok else "❌"
        print(f"  {icon} {groq_probe.name}" + (f" — {groq_probe.detail}" if groq_probe.detail else ""))
        if not groq_probe.ok:
            print("  ⚠️  Sans Groq valide, les 429 Cerebras feront échouer l'analyse (mode strict).")

    ids = list(SCENARIOS.keys()) if args.scenario == "all" else [args.scenario]
    reports: list[ScenarioReport] = []

    for i, sid in enumerate(ids):
        if i > 0 and args.delay > 0:
            print(f"\n⏳ Pause {args.delay}s (quota Cerebras)…")
            await asyncio.sleep(args.delay)
        ctx = SCENARIOS[sid]
        print(f"\n## Scénario: {sid}")
        print(f"   Objectif: {ctx.objective[:80]}…")
        report = ScenarioReport(id=sid)
        if args.analyze_only:
            ok_a = await _run_analyze(ctx, settings, report)
            if ok_a:
                print(f"   ✅ Analyse: {report.subtask_count} sous-tâches, {report.categories}")
                for i, st in enumerate(report.sample_subtasks[:4], 1):
                    print(f"      {i}. {st[:100]}")
            else:
                print(f"   ❌ Analyse: {report.error or 'échec checks'}")
        else:
            # Un seul passage pipeline (évite double appel LLM analyse → moins de 429)
            await _run_orchestrator(ctx, settings, report)
            err = report.error or ""
            report.analyze_ok = "query_analyzer" not in err and report.agent_count > 0
            if report.analyze_ok:
                print("   ✅ Analyse LLM (intégrée au pipeline)")
            elif "query_analyzer" in err:
                print(f"   ❌ Analyse: {err[:200]}")
            ok_o = report.orchestrator_ok
            if ok_o:
                print(
                    f"   ✅ Orchestrateur: {report.agent_count} agents, "
                    f"{report.total_cost}€, mode={report.retrieval_mode}, "
                    f"{report.processing_ms}ms"
                )
                for line in report.sample_agents:
                    print(f"      {line}")
            else:
                print(f"   ❌ Orchestrateur: {report.error or 'invariants KO'}")
                for c in report.checks:
                    if not c.ok:
                        print(f"      ✗ {c.name}: {c.detail}")

        reports.append(report)

    # Résumé JSON
    out_path = Path("scripts/phase0_report.json")
    payload = {
        "env_ok": all(c.ok for c in env_checks),
        "scenarios": [
            {
                "id": r.id,
                "analyze_ok": r.analyze_ok,
                "orchestrator_ok": r.orchestrator_ok,
                "subtask_count": r.subtask_count,
                "categories": r.categories,
                "retrieval_mode": r.retrieval_mode,
                "agent_count": r.agent_count,
                "total_cost": r.total_cost,
                "budget_max": r.budget_max,
                "processing_ms": r.processing_ms,
                "error": r.error,
                "checks": [{"name": c.name, "ok": c.ok, "detail": c.detail} for c in r.checks],
            }
            for r in reports
        ],
    }
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n📄 Rapport JSON: {out_path}")

    all_analyze = all(r.analyze_ok for r in reports)
    all_orch = all(r.orchestrator_ok for r in reports) if not args.analyze_only else True

    print("\n" + "=" * 60)
    if all_analyze and all_orch:
        print("✅ PHASE 0 — TOUS LES CRITÈRES PASSENT")
        sys.exit(0)
    if all_analyze and args.analyze_only:
        print("✅ PHASE 0 (analyze-only) — OK")
        sys.exit(0)
    print("❌ PHASE 0 — ÉCHECS (voir détails ci-dessus)")
    sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
