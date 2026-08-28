#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"

if [ ! -d "$ROOT/backend/.venv" ]; then
  python3 -m venv "$ROOT/backend/.venv"
  "$ROOT/backend/.venv/bin/pip" install -r "$ROOT/backend/requirements.txt"
fi

if [ ! -d "$ROOT/frontend/node_modules" ]; then
  (cd "$ROOT/frontend" && npm install)
fi

if [ ! -f "$ROOT/.env" ]; then
  cp "$ROOT/.env.example" "$ROOT/.env"
  echo "Created .env — add DISCORD_WEBHOOK_URL, DEST_GITHUB_TOKEN, DEST_GITHUB_ACCOUNT"
fi

(cd "$ROOT/frontend" && npm run build)

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-6001}"

"$ROOT/backend/.venv/bin/uvicorn" app.main:app \
  --reload \
  --reload-dir "$ROOT/backend/app" \
  --timeout-graceful-shutdown 3 \
  --host "$HOST" --port "$PORT" \
  --app-dir "$ROOT/backend"
