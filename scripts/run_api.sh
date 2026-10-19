#!/usr/bin/env bash
# Run the SimEval API locally with the development database.
# Usage: scripts/run_api.sh [host] [port]
set -euo pipefail

HOST="${1:-127.0.0.1}"
PORT="${2:-8000}"

if [ ! -x ".venv/bin/python" ]; then
  echo "error: .venv not found. Run 'make venv && make install && make dev-deps' first." >&2
  exit 1
fi

echo "Starting SimEval API on http://${HOST}:${PORT}"
echo "OpenAPI docs: http://${HOST}:${PORT}/docs"
exec .venv/bin/python -m uvicorn backend.app.main:app --host "${HOST}" --port "${PORT}" --reload
