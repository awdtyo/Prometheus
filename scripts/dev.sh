#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

if [ ! -d .venv ]; then
  echo "error: .venv not found. Run ./scripts/setup.sh first." >&2
  exit 1
fi

# shellcheck disable=SC1091
source .venv/bin/activate

HOST="${MISSION_AUTOPSY_API_HOST:-127.0.0.1}"
PORT="${MISSION_AUTOPSY_API_PORT:-8000}"
FRONTEND_DIR="$ROOT_DIR/frontend"
BACKEND_PID=""
FRONTEND_PID=""

if [ ! -x "$FRONTEND_DIR/node_modules/.bin/vite" ]; then
  echo "error: frontend dependencies not found. Run ./scripts/setup.sh first." >&2
  exit 1
fi

cleanup() {
  trap - EXIT INT TERM
  if [ -n "$BACKEND_PID" ]; then
    kill "$BACKEND_PID" 2>/dev/null || true
  fi
  if [ -n "$FRONTEND_PID" ]; then
    kill "$FRONTEND_PID" 2>/dev/null || true
  fi
  wait "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "==> Backend  http://$HOST:$PORT/docs"
echo "==> Frontend http://127.0.0.1:5173"

uvicorn backend.main:app --reload --host "$HOST" --port "$PORT" &
BACKEND_PID=$!

(
  cd "$FRONTEND_DIR"
  exec ./node_modules/.bin/vite --host 127.0.0.1
) &
FRONTEND_PID=$!

# Portable alternative to `wait -n` (which requires Bash 4.3+).
while kill -0 "$BACKEND_PID" 2>/dev/null && kill -0 "$FRONTEND_PID" 2>/dev/null; do
  sleep 1
done
