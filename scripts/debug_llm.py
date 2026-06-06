#!/usr/bin/env python3
"""Vérifie que .env charge bien Cerebras/Groq et teste un appel structured."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings
from app.domain.analyzed_query import QueryAnalyzerPass1Output
from app.infra.llm import create_llm_client


async def main() -> None:
    env_path = Path.cwd() / ".env"
    print(f"CWD: {Path.cwd()}")
    print(f".env existe: {env_path.is_file()} (requis — pas .env.example seul)")

    s = get_settings()
    cb_len = len((s.cerebras_api_key or "").strip())
    gq_len = len((s.groq_api_key or "").strip())
    print(f"CEREBRAS_API_KEY: {'OK (' + str(cb_len) + ' chars)' if cb_len else 'VIDE — colle ta clé dans .env'}")
    print(f"GROQ_API_KEY: {'OK (' + str(gq_len) + ' chars)' if gq_len else 'vide (optionnel)'}")
    print(f"Modèle Cerebras: {s.cerebras_model}")

    if env_path.is_file() and cb_len == 0 and gq_len == 0:
        print()
        print("Le fichier .env contient les lignes mais sans valeur après '='.")
        print("Exemple correct :")
        print("  CEREBRAS_API_KEY=csk_xxxxxxxx")
        print("(pas de guillemets, pas d'espace autour du =)")

    llm = create_llm_client(s)
    if not llm:
        print("❌ Aucun client LLM — renseigne au moins CEREBRAS_API_KEY dans .env")
        sys.exit(1)

    print(f"✓ Client: {llm.provider}")

    try:
        out = await llm.complete_structured(
            QueryAnalyzerPass1Output,
            'OBJECTIF: "Automatiser boutique Shopify SEO et support"\n'
            "Décompose en sous-tâches JSON avec catégories valides.",
            schema_name="debug_pass1",
            preferred_model="qwen-235b",
            max_tokens=800,
        )
        print("✓ LLM OK — sous-tâches:", len(out.subtasks))
        for st in out.subtasks[:5]:
            print(f"  - [{st.id}] {st.action[:80]}… ({st.required_category.value})")
    except Exception as exc:
        print(f"❌ Appel LLM: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
