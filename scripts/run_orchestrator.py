#!/usr/bin/env python3
"""Pipeline complet : analyse → Jina → Supabase → matcher → stack."""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings
from app.core.models import UserContext
from app.pipeline.orchestrator import run_orchestrator


async def main() -> None:
    if not Path(".env").is_file():
        print("❌ Crée un fichier .env (cp .env.example .env)")
        sys.exit(1)

    s = get_settings()
    missing = []
    if not (s.cerebras_api_key or "").strip() and not (s.groq_api_key or "").strip():
        missing.append("CEREBRAS_API_KEY ou GROQ_API_KEY")
    if not (s.jina_api_key or "").strip():
        missing.append("JINA_API_KEY")
    if not (s.supabase_url or "").strip() or not (s.supabase_service_role_key or "").strip():
        missing.append("SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY")
    if missing:
        print("❌ Variables manquantes dans .env:", ", ".join(missing))
        sys.exit(1)

    ctx = UserContext(
        objective="Automatiser ma boutique Shopify: SEO, emails clients et support",
        sector="ecommerce",
        budget="low",
        tech_level="beginner",
        locale="fr",
        preferred_model="qwen-235b",
    )

    print("🚀 Orchestrateur — pipeline complet (timeout 120s)…")
    result = await run_orchestrator(ctx, s)

    if not result:
        print("❌ Orchestrateur a échoué (voir logs ci-dessus)")
        sys.exit(1)

    stack = result.stack
    meta = result.meta
    print()
    print(f"✅ Stack: {stack.stack_name}")
    print(f"   Agents: {len(stack.agents)} | Coût: {stack.total_cost}€/mois")
    print(f"   Mode retrieval: {meta.retrieval_mode} | {meta.processing_time_ms}ms")
    print(f"   Embedding: {meta.embedding_latency_ms}ms")
    print()
    for a in stack.agents:
        print(f"  {a.rank}. {a.name} ({a.category}) — {a.price_from}€")
        print(f"     {a.role[:90]}…")
    print()
    print("Meta:", json.dumps(meta.model_dump(), indent=2))


if __name__ == "__main__":
    asyncio.run(main())
