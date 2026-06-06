# Phase 0 — Validation moteur standalone

Checklist avant branchement Next.js (Phase 3).

## Prérequis `.env`

```bash
cd raspquery-reco
cp .env.example .env   # si pas déjà fait
```

| Variable | Obligatoire | Note |
|----------|-------------|------|
| `CEREBRAS_API_KEY` | oui (prioritaire) | Qwen 235B |
| `GROQ_API_KEY` | **fortement recommandé** | Secours 429 ; doit être une clé **valide** (`gsk_…`) |
| `JINA_API_KEY` | oui | Embeddings |
| `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` | oui | RPC catalogue |
| `RECO_ALLOW_HEURISTIC_FALLBACK` | `false` | Pas de plan « à peu près » silencieux |

Vérifier Groq :

```bash
source .venv/bin/activate
python scripts/phase0_validate.py --analyze-only --scenario shopify
# doit afficher ✅ Groq probe si la clé est bonne
```

## Lancer la validation

```bash
source .venv/bin/activate

# Un scénario (recommandé pour éviter 429)
python scripts/phase0_validate.py --scenario shopify

# Les 3 scénarios avec pause 30s entre chaque
python scripts/phase0_validate.py --delay 30

# Analyse seule (sans Jina/Supabase stack)
python scripts/phase0_validate.py --analyze-only --scenario shopify
```

Rapport JSON : `scripts/phase0_report.json`

## Scénarios

| ID | Objectif | Budget max |
|----|----------|------------|
| `shopify` | Boutique Shopify + chatbot support | 50€ |
| `saas_b2b` | LinkedIn + prospection B2B | 200€ |
| `support` | Shopify SEO + emails + support | 50€ |

## Critères de succès (0.x)

- [ ] `.env` complet + `RECO_ALLOW_HEURISTIC_FALLBACK=false`
- [ ] Groq probe ✅ (sinon corriger `GROQ_API_KEY`)
- [ ] Analyse : ≥5 sous-tâches **concrètes**, pas heuristique
- [ ] Orchestrateur : `retrieval_mode=vector`
- [ ] Stack : 3–8 agents, **coût ≤ budget**
- [ ] Pas de 503 analyse en conditions normales (1 scénario à la fois)

## Comparaison TypeScript (0.3)

```bash
# Depuis raspquery-reco/ (recommandé — rapport JSON + Jaccard agents)
python scripts/compare_ts_py.py --delay 45

# Un seul scénario
python scripts/compare_ts_py.py --scenario shopify --delay 60

# Rapport : scripts/compare_ts_py_report.json
```

Prérequis :

- `raspquery-reco/.env` avec **SUPABASE_URL** + **SUPABASE_SERVICE_ROLE_KEY** (source de vérité)
- `stackai/.env.local` optionnel (Clerk, etc.) — le script TS mappe `SUPABASE_URL` → `NEXT_PUBLIC_SUPABASE_URL`
- `cd ../stackai && npm install` si besoin

Test TS seul :

```bash
cd ../stackai
npx tsx scripts/export-orchestrator-result.ts shopify
# doit afficher [export] Supabase host: ojrarkplhybsgohjgeip.supabase.co (pas placeholder)
```

Alternative Vitest :

```bash
cd ../stackai
RUN_LIVE_LLM_TESTS=1 npx vitest run lib/agents/__tests__/orchestrator.integration.test.ts
```

Voir aussi [docs/CEREBRAS_429.md](../docs/CEREBRAS_429.md) (pourquoi les 429 ne signifient pas que Cerebras est KO).

## Problèmes connus → Phase 1

| Symptôme | Cause | Suite |
|----------|-------|-------|
| 429 Cerebras en rafale | 3 scénarios × 4+ appels LLM | `--delay 30`, 1 scénario à la fois |
| Groq 401 | Clé invalide / placeholder dans `.env` | Nouvelle clé sur [console.groq.com](https://console.groq.com) |
| `stack_selection` JSON tronqué | Réponse LLM trop longue / 429 | Fallback scoring + top 12 candidats (corrigé) |
| 2 agents après redondance | 2 chatbots dans le même groupe | Refill post-redondance (corrigé) |
| Budget dépassé (ex. 246€ > 200€) | `stack_builder` trim faible | Phase 1 — parité TS |
| 503 analyse | Cerebras saturé + pas de Groq | Corriger Groq ou attendre 1 min |
