# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm AS builder

WORKDIR /build

RUN pip install --no-cache-dir --upgrade pip setuptools wheel

COPY pyproject.toml README.md ./
COPY app ./app

RUN pip install --no-cache-dir .

# ─── Runtime ───────────────────────────────────────────────────────────────────
FROM python:3.12-slim-bookworm

WORKDIR /app

RUN groupadd --system reco && useradd --system --gid reco --uid 10001 reco

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY app ./app
COPY pyproject.toml README.md ./
COPY data/catalog-filter.json ./data/catalog-filter.json
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    RECO_HOST=0.0.0.0 \
    RECO_PORT=8000 \
    CATALOG_FILTER_PATH=/app/data/catalog-filter.json

EXPOSE 8000

USER reco

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\", os.environ.get(\"RECO_PORT\", \"8000\"))}/health')" || exit 1

ENTRYPOINT ["/app/docker-entrypoint.sh"]
