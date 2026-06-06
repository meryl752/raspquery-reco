#!/bin/sh
set -eu
PORT="${PORT:-${RECO_PORT:-8000}}"
exec uvicorn app.main:app \
  --host "${RECO_HOST:-0.0.0.0}" \
  --port "$PORT" \
  --workers 1 \
  --timeout-keep-alive 130
