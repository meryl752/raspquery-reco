#!/usr/bin/env python3
"""Audit raspquery-reco/.env — présence des clés sans afficher les secrets."""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings

REQUIRED = (
    ("CEREBRAS_API_KEY", "ou GROQ_API_KEY"),
    ("JINA_API_KEY", ""),
    ("SUPABASE_URL", ""),
    ("SUPABASE_SERVICE_ROLE_KEY", ""),
)
OPTIONAL = ("GROQ_API_KEY", "RECO_ALLOW_HEURISTIC_FALLBACK", "RECO_LLM_STEP_DELAY_MS")


def audit_dotenv_file(path: Path) -> None:
    print(f"\n## Fichier {path}")
    if not path.is_file():
        print("   ❌ absent")
        return
    lines = path.read_text(encoding="utf-8").splitlines()
    keys_seen: dict[str, list[int]] = {}
    empty_values: list[str] = []
    for i, line in enumerate(lines, 1):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if "=" not in s:
            print(f"   ⚠️  ligne {i}: pas une variable KEY=value")
            continue
        key, _, val = s.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        keys_seen.setdefault(key, []).append(i)
        if not val:
            empty_values.append(f"{key} (ligne {i})")

    for key, line_nums in sorted(keys_seen.items()):
        if len(line_nums) > 1:
            print(f"   ⚠️  doublon {key}: lignes {line_nums} (la dernière gagne avec pydantic)")

    if empty_values:
        print("   ❌ Valeurs vides (à supprimer ou remplir):")
        for e in empty_values:
            print(f"      - {e}")
    else:
        print("   ✅ Aucune ligne KEY= vide")


def main() -> None:
    root = Path.cwd()
    env_path = root / ".env"
    example_path = root / ".env.example"

    print("=" * 60)
    print("AUDIT .env — raspquery-reco")
    print("=" * 60)
    print(f"Répertoire: {root}")

    audit_dotenv_file(env_path)
    if example_path.is_file():
        print("\n(note: .env.example est un modèle — pydantic lit .env, pas .example)")

    s = get_settings()

    def ok(v: str | None) -> bool:
        return bool((v or "").strip())

    print("\n## Chargement pydantic (get_settings)")
    cerebras = ok(s.cerebras_api_key)
    groq = ok(s.groq_api_key)
    print(f"   {'✅' if cerebras else '❌'} CEREBRAS_API_KEY ({len((s.cerebras_api_key or '').strip())} caractères)")
    print(f"   {'✅' if groq else '○'} GROQ_API_KEY ({len((s.groq_api_key or '').strip())} caractères)")
    print(f"   {'✅' if ok(s.jina_api_key) else '❌'} JINA_API_KEY")
    print(f"   {'✅' if ok(s.supabase_url) else '❌'} SUPABASE_URL")
    if ok(s.supabase_url):
        host = re.sub(r"^https?://", "", s.supabase_url.strip()).split("/")[0]
        print(f"      host: {host}")
    print(f"   {'✅' if ok(s.supabase_service_role_key) else '❌'} SUPABASE_SERVICE_ROLE_KEY")

    if not cerebras and not groq:
        print("\n❌ Aucun LLM chargé — le .env est vide ou mal formaté.")
        print("   cp .env.example .env")
        print("   Puis édite .env : CEREBRAS_API_KEY=csk_... (sans guillemets)")
        sys.exit(1)

    if not ok(s.supabase_url):
        print("\n❌ SUPABASE_URL vide après chargement — supprime SUPABASE_URL= sans valeur")
        sys.exit(1)

    print("\n✅ .env utilisable par le moteur Python")


if __name__ == "__main__":
    main()
