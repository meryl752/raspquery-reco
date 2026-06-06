# Pourquoi Cerebras affiche des 429 (et ce n’est pas « cassé »)

## Ce que tu vois dans les logs

```text
Cerebras HTTP 429 — queue_exceeded
Cerebras HTTP 429 — request_quota_exceeded
```

Puis souvent : **Groq prend le relais** ou un **fallback programmatique** (sélection par score, enrichissement catalogue).

Le pipeline **ne s’arrête pas** : Phase 0 peut passer avec des 429, comme dans tes runs.

## Causes (pas un bug de clé API)

| Cause | Détail |
|-------|--------|
| **Quota / file d’attente** | Plan Cerebras limité en requêtes/minute ou saturation globale (`queue_exceeded`) |
| **Rafale d’appels** | Un seul `/recommend` = **4 à 6 appels LLM** : analyse pass1, pass2, sélection stack, enrichissement |
| **Validation en rafale** | `phase0_validate` ou `compare_ts_py` enchaînent **3 scénarios** → dizaines d’appels en quelques minutes |
| **Retries** | Chaque 429 déclenche jusqu’à 4 retries → multiplie la charge |

Le monolithe TS a le **même risque** ; il utilise aussi `withProviderRetries` + Groq. En dev tu lances souvent **un** scénario à la fois, donc moins de 429 visibles.

## Pourquoi Groq « sauve » le run

Ordre dans `LlmClient` :

1. Cerebras Qwen 235B (+ fallback gpt-oss-120b)
2. Si échec → **Groq** (qwen3-32b → llama-3.3)

Avec `GROQ_API_KEY` valide, l’analyse et parfois le stack builder passent même quand Cerebras est saturé.

## Réduire les 429 (sans changer de modèle)

```env
# raspquery-reco/.env
RECO_LLM_STEP_DELAY_MS=800   # ou 1000 entre étapes LLM
```

```bash
# Un scénario à la fois
python scripts/phase0_validate.py --scenario shopify --delay 45
python scripts/compare_ts_py.py --scenario shopify --delay 60
```

## Comparaison TS vs PY — timeout TypeScript

Le monolithe `stackai` avait un timeout orchestrateur **45 s** (Python : **120 s**).  
Le script `export-orchestrator-result.ts` utilise maintenant `process.exit()` après export pour ne pas bloquer 3 min sur des LLM en arrière-plan.

Variables passées par `compare_ts_py.py` :

- `ORCHESTRATOR_TIMEOUT_MS=120000`
- `EXPORT_ORCHESTRATOR_TIMEOUT_MS=125000`

- Espacer **compare_ts_py** : `--delay 45` (défaut) entre Python et TS, et entre scénarios.
- Éviter de lancer validate + compare + dev server en parallèle sur la même clé Cerebras.

## Ce qui ne garantit pas 0 % d’échec

Même avec retries + Groq, un pic global Cerebras (`queue_exceeded`) peut faire échouer **tous** les modèles Cerebras d’un coup ; Groq reste alors le seul chemin qualité.

**Garantie produit actuelle** : pas de reco heuristique silencieuse (`RECO_ALLOW_HEURISTIC_FALLBACK=false`) → LLM ou erreur explicite, pas un plan bidon.

## Piste prod (plus tard)

- Cache analyse par hash d’objectif (TTL court)
- File d’attente / rate limiter global côté reco service
- Tier Cerebras plus haut ou répartition des appels (enrichissement seulement sur Groq)
