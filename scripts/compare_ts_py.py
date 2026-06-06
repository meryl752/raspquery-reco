#!/usr/bin/env python3
"""
Comparaison moteur TypeScript (stackai) vs Python (raspquery-reco) — 3 scénarios Phase 0.

Usage (venv activé, depuis raspquery-reco/) :
  python scripts/compare_ts_py.py
  python scripts/compare_ts_py.py --scenario shopify
  python scripts/compare_ts_py.py --py-only
  python scripts/compare_ts_py.py --delay 45

Prérequis :
  - raspquery-reco/.env (Cerebras, Groq, Jina, Supabase)
  - stackai/.env.local (mêmes clés pour le moteur TS)
  - Node : cd ../stackai && npm install (si besoin)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings
from app.core.models import UserContext
from app.pipeline.orchestrator import run_orchestrator

ROOT = Path(__file__).resolve().parents[1]
STACKAI_ROOT = ROOT.parent / "stackai"
SCENARIOS_PATH = Path(__file__).resolve().parent / "phase0_scenarios.json"
TS_EXPORT = STACKAI_ROOT / "scripts/export-orchestrator-result.ts"
REPORT_PATH = Path(__file__).resolve().parent / "compare_ts_py_report.json"


def load_scenarios() -> dict[str, dict]:
    return json.loads(SCENARIOS_PATH.read_text(encoding="utf-8"))


def to_user_context(payload: dict) -> UserContext:
    return UserContext(
        objective=payload["objective"],
        sector=payload["sector"],
        team_size=payload.get("team_size", "solo"),
        budget=payload["budget"],
        tech_level=payload["tech_level"],
        timeline=payload.get("timeline", "weeks"),
        current_tools=payload.get("current_tools", []),
        locale=payload.get("locale", "fr"),
        preferred_model=payload.get("preferred_model", "qwen-235b"),
    )


def snapshot_from_py(scenario_id: str, ctx: UserContext, result) -> dict:
    stack = result.stack
    meta = result.meta
    return {
        "engine": "python",
        "scenario": scenario_id,
        "objective": ctx.objective,
        "budget": ctx.budget,
        "stack_name": stack.stack_name,
        "total_cost": stack.total_cost,
        "roi_estimate": stack.roi_estimate,
        "agent_count": len(stack.agents),
        "agent_names": [a.name for a in stack.agents],
        "agents": [
            {
                "name": a.name,
                "category": a.category,
                "price_from": a.price_from,
                "role": (a.role or "")[:120],
            }
            for a in stack.agents
        ],
        "subtask_count": meta.subtasks_detected,
        "retrieval_mode": meta.retrieval_mode,
        "processing_ms": meta.processing_time_ms,
        "warnings_count": len(stack.warnings or []),
    }


async def run_python(scenario_id: str, payload: dict) -> dict:
    ctx = to_user_context(payload)
    settings = get_settings()
    t0 = time.perf_counter()
    result = await run_orchestrator(ctx, settings)
    elapsed = int((time.perf_counter() - t0) * 1000)
    if not result:
        return {
            "engine": "python",
            "scenario": scenario_id,
            "error": "orchestrator returned None",
            "processing_ms": elapsed,
        }
    snap = snapshot_from_py(scenario_id, ctx, result)
    snap["processing_ms"] = meta_ms if (meta_ms := snap.get("processing_ms")) else elapsed
    return snap


def _typescript_subprocess_env() -> dict[str, str]:
    """Pousse les clés raspquery-reco/.env vers les noms attendus par stackai."""
    settings = get_settings()
    env = os.environ.copy()
    if (settings.supabase_url or "").strip():
        url = settings.supabase_url.strip()
        env["SUPABASE_URL"] = url
        env["NEXT_PUBLIC_SUPABASE_URL"] = url
    if (settings.supabase_service_role_key or "").strip():
        env["SUPABASE_SERVICE_ROLE_KEY"] = settings.supabase_service_role_key.strip()
    if (settings.jina_api_key or "").strip():
        env["JINA_API_KEY"] = settings.jina_api_key.strip()
    if (settings.cerebras_api_key or "").strip():
        env["CEREBRAS_API_KEY"] = settings.cerebras_api_key.strip()
    if (settings.groq_api_key or "").strip():
        env["GROQ_API_KEY"] = settings.groq_api_key.strip()
    env.setdefault("ORCHESTRATOR_TIMEOUT_MS", "120000")
    env.setdefault("EXPORT_ORCHESTRATOR_TIMEOUT_MS", "125000")
    return env


def run_typescript(scenario_id: str, timeout_s: int = 300) -> dict:
    if not TS_EXPORT.is_file():
        return {
            "engine": "typescript",
            "scenario": scenario_id,
            "error": f"Script TS introuvable: {TS_EXPORT}",
        }
    if not (STACKAI_ROOT / "node_modules").is_dir():
        return {
            "engine": "typescript",
            "scenario": scenario_id,
            "error": "Exécutez: cd ../stackai && npm install",
        }

    cmd = ["npx", "tsx", str(TS_EXPORT), scenario_id]
    env = _typescript_subprocess_env()
    if not env.get("NEXT_PUBLIC_SUPABASE_URL"):
        return {
            "engine": "typescript",
            "scenario": scenario_id,
            "error": "SUPABASE_URL manquant dans raspquery-reco/.env",
        }
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(STACKAI_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout_s,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return {
            "engine": "typescript",
            "scenario": scenario_id,
            "error": f"timeout après {timeout_s}s",
        }

    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()

    if proc.returncode != 0:
        return {
            "engine": "typescript",
            "scenario": scenario_id,
            "error": stderr[-500:] or stdout[-500:] or f"exit {proc.returncode}",
        }

    # Dernière ligne JSON (logs éventuels au-dessus)
    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        return {
            "engine": "typescript",
            "scenario": scenario_id,
            "error": "sortie non JSON",
            "raw_tail": stdout[-400:],
        }


def jaccard(a: list[str], b: list[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 1.0
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def compare_pair(py: dict, ts: dict) -> dict:
    if py.get("error") or ts.get("error"):
        return {
            "ok": False,
            "error": py.get("error") or ts.get("error"),
        }

    names_py = py.get("agent_names") or []
    names_ts = ts.get("agent_names") or []
    overlap = sorted(set(names_py) & set(names_ts))
    only_py = sorted(set(names_py) - set(names_ts))
    only_ts = sorted(set(names_ts) - set(names_py))

    cost_py = py.get("total_cost")
    cost_ts = ts.get("total_cost")
    cost_delta = None
    if isinstance(cost_py, (int, float)) and isinstance(cost_ts, (int, float)):
        cost_delta = round(float(cost_py) - float(cost_ts), 1)

    return {
        "ok": True,
        "agents_jaccard": round(jaccard(names_py, names_ts), 2),
        "agents_overlap": overlap,
        "only_python": only_py,
        "only_typescript": only_ts,
        "cost_python": cost_py,
        "cost_typescript": cost_ts,
        "cost_delta_py_minus_ts": cost_delta,
        "retrieval_python": py.get("retrieval_mode"),
        "retrieval_typescript": ts.get("retrieval_mode"),
        "subtasks_python": py.get("subtask_count"),
        "subtasks_typescript": ts.get("subtask_count"),
        "stack_name_python": py.get("stack_name"),
        "stack_name_typescript": ts.get("stack_name"),
        "processing_ms_python": py.get("processing_ms"),
        "processing_ms_typescript": ts.get("processing_ms"),
    }


def print_comparison(scenario_id: str, comp: dict, py: dict, ts: dict) -> None:
    print(f"\n## {scenario_id}")
    if not comp.get("ok"):
        print(f"   ❌ {comp.get('error', 'erreur')}")
        return

    jac = comp["agents_jaccard"]
    icon = "✅" if jac >= 0.4 else "⚠️"
    print(f"   {icon} Similarité agents (Jaccard): {jac:.0%}")
    print(f"   Communs: {', '.join(comp['agents_overlap']) or '—'}")
    if comp["only_python"]:
        print(f"   Seulement Python: {', '.join(comp['only_python'])}")
    if comp["only_typescript"]:
        print(f"   Seulement TypeScript: {', '.join(comp['only_typescript'])}")
    print(
        f"   Coût: PY {comp['cost_python']}€ | TS {comp['cost_typescript']}€ "
        f"(Δ {comp['cost_delta_py_minus_ts']:+.1f}€)"
    )
    print(
        f"   Retrieval: PY {comp['retrieval_python']} | TS {comp['retrieval_typescript']}"
    )
    print(
        f"   Sous-tâches: PY {comp['subtasks_python']} | TS {comp['subtasks_typescript']}"
    )
    print(f"   Stack: PY «{comp['stack_name_python']}» | TS «{comp['stack_name_typescript']}»")
    print(
        f"   Durée: PY {comp['processing_ms_python']}ms | TS {comp['processing_ms_typescript']}ms"
    )


async def main() -> None:
    parser = argparse.ArgumentParser(description="Compare TS vs PY reco engines")
    parser.add_argument("--scenario", choices=["shopify", "saas_b2b", "support", "all"], default="all")
    parser.add_argument("--py-only", action="store_true")
    parser.add_argument("--ts-only", action="store_true")
    parser.add_argument(
        "--delay",
        type=int,
        default=45,
        help="Pause (s) entre chaque run LLM (évite 429 Cerebras)",
    )
    parser.add_argument(
        "--timeout-ts",
        type=int,
        default=300,
        help="Timeout subprocess TS (défaut 300s, pipeline ~2 min)",
    )
    args = parser.parse_args()

    scenarios = load_scenarios()
    ids = list(scenarios.keys()) if args.scenario == "all" else [args.scenario]

    print("=" * 60)
    print("COMPARAISON TS (stackai) vs PY (raspquery-reco)")
    print("=" * 60)
    print(f"Scénarios: {', '.join(ids)} | délai entre runs: {args.delay}s")

    report: dict = {"scenarios": {}, "notes": []}

    for i, sid in enumerate(ids):
        if i > 0 and args.delay > 0:
            print(f"\n⏳ Pause {args.delay}s (quota API)…")
            time.sleep(args.delay)

        payload = scenarios[sid]
        py_snap: dict | None = None
        ts_snap: dict | None = None

        if not args.ts_only:
            print(f"\n▶ Python — {sid}…")
            py_snap = await run_python(sid, payload)
            if py_snap.get("error"):
                print(f"   ❌ {py_snap['error']}")
            else:
                print(
                    f"   ✅ {py_snap['agent_count']} agents, {py_snap['total_cost']}€ — "
                    f"{', '.join(py_snap['agent_names'])}"
                )

        if args.delay > 0 and not args.py_only and not args.ts_only:
            print(f"⏳ Pause {args.delay}s avant TypeScript…")
            time.sleep(args.delay)

        if not args.py_only:
            print(f"\n▶ TypeScript — {sid}…")
            ts_snap = run_typescript(sid, timeout_s=args.timeout_ts)
            if ts_snap.get("error"):
                print(f"   ❌ {ts_snap['error'][:200]}")
            else:
                print(
                    f"   ✅ {ts_snap['agent_count']} agents, {ts_snap['total_cost']}€ — "
                    f"{', '.join(ts_snap['agent_names'])}"
                )

        if py_snap and ts_snap:
            comp = compare_pair(py_snap, ts_snap)
            report["scenarios"][sid] = {"python": py_snap, "typescript": ts_snap, "diff": comp}
            print_comparison(sid, comp, py_snap, ts_snap)
        else:
            report["scenarios"][sid] = {"python": py_snap, "typescript": ts_snap}

    REPORT_PATH.write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\n📄 Rapport: {REPORT_PATH}")
    print("\n" + "=" * 60)
    print("Fin comparaison — analyser agents_overlap / only_python / only_typescript")


if __name__ == "__main__":
    asyncio.run(main())
