#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "error: $PYTHON_BIN not found. Install Python 3.11+ and retry." >&2
  exit 1
fi

if ! "$PYTHON_BIN" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'; then
  echo "error: Python 3.11+ is required." >&2
  exit 1
fi

if [ ! -d .venv ]; then
  echo "==> Creating .venv"
  "$PYTHON_BIN" -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

echo "==> Installing Python dependencies"
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"

if [ ! -f .env ]; then
  cp .env.example .env
  echo "==> Created .env from .env.example (placeholders only)"
fi

if command -v npm >/dev/null 2>&1; then
  echo "==> Installing frontend dependencies"
  npm --prefix frontend install
else
  echo "warning: npm not found. Install Node.js 20.19+ and run:" >&2
  echo "  npm --prefix frontend install" >&2
fi

echo
echo "Setup complete."
echo "  Run both services: ./scripts/dev.sh"
echo "  Backend only:      source .venv/bin/activate && uvicorn backend.main:app --reload"
echo "  Frontend only:     npm --prefix frontend run dev"
