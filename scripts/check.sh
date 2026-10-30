#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [ ! -d .venv ]; then
  echo "error: .venv not found. Run ./scripts/setup.sh first." >&2
  exit 1
fi

# shellcheck disable=SC1091
source .venv/bin/activate

echo "==> Ruff lint"
ruff check autopsy backend tests

echo "==> Ruff format"
ruff format --check autopsy backend tests

echo "==> mypy"
mypy autopsy backend

echo "==> pytest"
pytest

echo "==> Frontend lint"
npm --prefix frontend run lint

echo "==> Frontend build"
npm --prefix frontend run build

echo
echo "All checks passed."
