#!/usr/bin/env bash
# One-command local development: start the backend and the dashboard together.
#
#   scripts/dev.sh            # backend on :8000, dashboard on :5173
#   scripts/dev.sh 8000 5173  # custom ports
#
# Ctrl-C stops both.
set -euo pipefail

API_PORT="${1:-8000}"
WEB_PORT="${2:-5173}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [ ! -x ".venv/bin/python" ]; then
  echo "error: .venv missing. Run: make venv && make install && make dev-deps" >&2
  exit 1
fi
if [ ! -d "frontend/node_modules" ]; then
  echo "Installing frontend dependencies…"
  (cd frontend && npm install)
fi

echo "Applying database migrations…"
.venv/bin/alembic upgrade head

cleanup() {
  echo
  echo "Shutting down…"
  kill 0 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "Starting backend on http://127.0.0.1:${API_PORT} (docs at /docs)"
.venv/bin/python -m uvicorn backend.app.main:app --host 127.0.0.1 --port "$API_PORT" &
API_PID=$!

echo "Starting dashboard on http://127.0.0.1:${WEB_PORT}"
(cd frontend && npm run dev -- --port "$WEB_PORT" --host 127.0.0.1) &
WEB_PID=$!

wait -n "$API_PID" "$WEB_PID"
