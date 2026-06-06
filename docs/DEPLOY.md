# Déploiement — raspquery-reco

Moteur Python exposé en `POST /v1/recommend`. Next.js (Vercel) reste la porte d’entrée produit.

## Prérequis secrets

| Variable | Obligatoire |
|----------|-------------|
| `CEREBRAS_API_KEY` ou `GROQ_API_KEY` | au moins un LLM |
| `JINA_API_KEY` | embeddings |
| `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` | catalogue |
| `RECO_INTERNAL_API_KEY` | **prod** (même valeur que `RECO_ENGINE_API_KEY` côté Vercel) |
| `RECO_CORS_ORIGINS` | URL Next prod, ex. `https://app.raspquery.com` |

Optionnel : `RECO_LLM_STEP_DELAY_MS=800`, `RECO_ALLOW_HEURISTIC_FALLBACK=false`

## Build & run local (Docker)

```bash
cd raspquery-reco
cp .env.example .env   # remplir les clés
docker compose up --build
```

- Liveness : `GET http://localhost:8000/health`
- Readiness : `GET http://localhost:8000/health/ready` (503 si `.env` incomplet)

Test reco :

```bash
curl -s -X POST http://localhost:8000/v1/recommend \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: $RECO_INTERNAL_API_KEY" \
  -d '{"objective":"Automatiser support Shopify avec chatbot","sector":"ecommerce","budget":"low","tech_level":"beginner","locale":"fr"}' | head -c 500
```

## Railway (recommandé — budget limité)

### 1. Repo GitHub

```bash
cd raspquery-reco
git init
git add .
git commit -m "feat: moteur reco Python — Docker + Railway"
# Créer le repo vide sur GitHub : raspquery-reco
git remote add origin https://github.com/VOTRE_USER/raspquery-reco.git
git branch -M main
git push -u origin main
```

### 2. Projet Railway

1. [railway.app](https://railway.app) → **New Project** → **Deploy from GitHub repo** → `raspquery-reco`
2. Railway détecte le **Dockerfile** (`railway.toml` → healthcheck `/health`)
3. **Settings → Networking → Generate Domain** → noter l’URL (`https://xxx.up.railway.app`)

### 3. Variables (Railway → Variables)

Générer un secret partagé :

```bash
openssl rand -hex 32
```

| Variable | Valeur |
|----------|--------|
| `CEREBRAS_API_KEY` | (ou `GROQ_API_KEY` minimum) |
| `GROQ_API_KEY` | recommandé en secours |
| `JINA_API_KEY` | embeddings |
| `SUPABASE_URL` | même projet que Vercel |
| `SUPABASE_SERVICE_ROLE_KEY` | clé service role |
| `RECO_INTERNAL_API_KEY` | secret généré ci-dessus |
| `RECO_CORS_ORIGINS` | URL Vercel prod, ex. `https://agent-advisor.vercel.app` |
| `RECO_ALLOW_HEURISTIC_FALLBACK` | `false` |
| `CATALOG_FILTER_PATH` | `/app/data/catalog-filter.json` |

Railway injecte `PORT` automatiquement — le Dockerfile s’adapte.

### 4. Vérifier le deploy

```bash
curl https://xxx.up.railway.app/health/ready
```

Réponse `"status": "ready"` avec les 3 checks à `true`. Si **503 degraded** : variable manquante — utiliser les noms **`SUPABASE_URL`** (pas `NEXT_PUBLIC_*`), etc.

Le healthcheck Railway utilise `/health` (process vivant). `/health/ready` valide les secrets manuellement.

Test reco :

```bash
curl -s -X POST https://xxx.up.railway.app/v1/recommend \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: $RECO_INTERNAL_API_KEY" \
  -d '{"objective":"Automatiser support Shopify","sector":"ecommerce","budget":"low","tech_level":"beginner","locale":"fr"}' | head -c 400
```

### 5. Brancher Vercel

Variables **Production** (Settings → Environment Variables) :

```env
RECO_ENGINE_ENABLED=true
RECO_ENGINE_URL=https://xxx.up.railway.app
RECO_ENGINE_API_KEY=<même secret que RECO_INTERNAL_API_KEY>
RECO_ENGINE_FALLBACK_TS=true
RECO_ENGINE_TIMEOUT_MS=120000
```

Redéployer Vercel (ou attendre le redeploy auto). Une reco UI doit renvoyer `meta.engine: "python"`.

**Coût :** Railway facture à l’usage (~5–10 €/mois si le service tourne en continu). Désactiver le service quand tu n’en as pas besoin pour économiser.

### Dépannage — « Healthcheck failure »

1. **Cause fréquente** : healthcheck sur `/health/ready` → **503** tant qu’une clé API manque. Fix : healthcheck sur `/health` (déjà dans `railway.toml` du repo).
2. Vérifier les **Deploy Logs** (crash uvicorn, permissions).
3. Noms exacts des variables sur Railway (table ci-dessus).
4. Après deploy vert : `curl …/health/ready` pour confirmer les secrets.

## Fly.io

```bash
cd raspquery-reco
fly launch --no-deploy   # ou fly apps create raspquery-reco
fly secrets set CEREBRAS_API_KEY=... GROQ_API_KEY=... JINA_API_KEY=... \
  SUPABASE_URL=... SUPABASE_SERVICE_ROLE_KEY=... \
  RECO_INTERNAL_API_KEY=... \
  RECO_CORS_ORIGINS=https://votre-app.vercel.app
fly deploy
fly status
```

URL publique → `https://raspquery-reco.fly.dev` (selon votre app).

## Brancher Vercel (stackai)

Variables **Production** / Preview :

```env
RECO_ENGINE_ENABLED=true
RECO_ENGINE_URL=https://raspquery-reco.fly.dev
RECO_ENGINE_API_KEY=<même secret que RECO_INTERNAL_API_KEY>
RECO_ENGINE_FALLBACK_TS=true
RECO_ENGINE_TIMEOUT_MS=120000
```

Sans fallback strict : `RECO_ENGINE_FALLBACK_TS=false` (Python only).

Après deploy : une reco UI doit renvoyer `meta.engine: "python"` dans la réponse `/api/recommend`.

## Railway / Render

1. Service Docker, root `raspquery-reco`, Dockerfile présent.
2. Port **8000**, health check path `/health/ready`.
3. Coller les mêmes secrets que Fly.
4. Copier l’URL publique dans `RECO_ENGINE_URL` sur Vercel.

## Sync catalogue ICP

Le fichier `data/catalog-filter.json` est embarqué dans l’image. Après modification côté `stackai/data/catalog-filter.json` :

```bash
cp ../stackai/data/catalog-filter.json data/catalog-filter.json
docker compose build
```

## Workers

Une reco peut durer **60–120 s**. Garder **1 worker** uvicorn par instance ; scaler horizontalement si besoin (plusieurs machines Fly), pas plusieurs workers sur une petite VM (mémoire).
