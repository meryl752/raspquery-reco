#!/usr/bin/env python3
"""Test local du query analyzer — utilise le venv du projet."""

import asyncio
import sys
from pathlib import Path  # noqa: F401 — used below

# Permet `python scripts/analyze_query.py` depuis raspquery-reco/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings
from app.core.models import UserContext
from app.infra.llm import create_llm_client
from app.pipeline.query_analyzer import analyze_query


async def main() -> None:
    ctx = UserContext(
        objective="Automatiser ma boutique Shopify: SEO, emails clients et support",
        sector="ecommerce",
        budget="low",
        tech_level="beginner",
        locale="fr",
        preferred_model="qwen-235b",
    )
    settings = get_settings()
    llm = create_llm_client(settings)
    if not Path(".env").is_file():
        print("❌ Fichier .env manquant. Les clés dans .env.example ne sont PAS lues.")
        print("   → cp .env.example .env   puis édite .env avec CEREBRAS_API_KEY")
        sys.exit(1)
    if not llm:
        print("❌ Configure CEREBRAS_API_KEY (Qwen 235B) ou GROQ_API_KEY dans .env")
        sys.exit(1)

    print(f"LLM provider: {llm.provider} (preferred={ctx.preferred_model})")
    q = await analyze_query(ctx, llm, settings)
    # Fallback heuristique = actions du type "seo: contribuer à l'objectif — …"
    if q.subtasks and q.subtasks[0].startswith(
        ("seo:", "automation:", "customer_service:", "copywriting:")
    ):
        print("⚠️  Sortie probablement HEURISTIQUE (pas le LLM).")
    print(f"Domaines: {len(q.domains)}")
    for d in q.domains:
        print(f"  • {d.name} ({len(d.subtasks)} tâches)")
    print("Catégories:", q.required_category_values)
    print("Sous-tâches:")
    for i, st in enumerate(q.subtasks, 1):
        print(f"  {i}. {st}")


if __name__ == "__main__":
    asyncio.run(main())
