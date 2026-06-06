# Raspquery Reco — moteur Python

Backend **greenfield** pour la recommandation de stacks IA. Il vit à côté de `stackai/` (Next.js) et **ne remplace rien** tant que vous ne basculez pas explicitement l’appel API.

## Principes

| Dossier | Rôle |
|---------|------|
| `stackai/` | UI, Clerk, quotas, persistance, Stack Health — **inchangé** |
| `raspquery-reco/` | Pipeline reco pur : analyse → retrieval → match → stack |

Le contrat HTTP `POST /v1/recommend` reprend les champs de `recommendSchema` et renvoie un `OrchestratorResult` compatible avec ce que consomme aujourd’hui `/api/recommend`.

## Démarrage local

```bash
cd raspquery-reco
python3 -m venv .venv
source .venv/bin/activate   # pas "venv" — le dossier s'appelle .venv
pip install -e ".[dev]"
cp .env.example .env
# Qwen 235B : CEREBRAS_API_KEY + CEREBRAS_MODEL=qwen-3-235b-a22b-instruct-2507
# Secours : GROQ_API_KEY
uvicorn app.main:app --reload --port 8000
```

Test query analyzer (avec le venv activé) :

```bash
source .venv/bin/activate
python scripts/analyze_query.py
```

Pipeline complet (nécessite `.env` : Cerebras, Jina, Supabase) :

```bash
python scripts/run_orchestrator.py
```

**Phase 0 — validation prod** (checklist + 3 scénarios) :

```bash
python scripts/phase0_validate.py --scenario shopify
# voir scripts/PHASE0.md
```

- Santé : `GET /health`
- Reco : `POST /v1/recommend` (voir `app/api/schemas.py`)

## Pipeline

```
UserContext
  → query_analyzer   (LLM — domaines / sous-tâches)
  → embeddings + supabase RPC (smart_search_agents)
  → matcher          (RRF vectoriel + métier — porté depuis le TS)
  → stack_builder    (LLM — sélection finale + enrichissement)
  → OrchestratorResult
```

`query_analyzer` et `stack_builder` sont portés depuis `stackai/lib/agents/` (prompts, rôles, `roi_score`, filtres budget/redondance).

## Brancher Next.js

Dans `stackai/.env.local` :

```env
RECO_ENGINE_ENABLED=true
RECO_ENGINE_URL=http://localhost:8000
RECO_ENGINE_API_KEY=...          # = RECO_INTERNAL_API_KEY côté Python (prod)
RECO_ENGINE_FALLBACK_TS=true     # secours orchestrateur TS si Python KO
```

La route `/api/recommend` proxy vers `POST /v1/recommend`. Réponse : `meta.engine` = `python` | `typescript`.

## Déploiement Docker / Fly

```bash
docker compose up --build    # local
# ou fly deploy — voir docs/DEPLOY.md
```

## Tests

```bash
pytest
```
