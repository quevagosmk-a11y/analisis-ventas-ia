#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

PYTHON_BIN="python3"
if [[ -x ".venv/bin/python" ]]; then
  PYTHON_BIN=".venv/bin/python"
fi

echo "[1/5] Verificando sintaxis Python..."
"$PYTHON_BIN" -m compileall -q src

echo "[2/5] Ejecutando tests Python..."
"$PYTHON_BIN" -m pytest -q

echo "[3/5] Ejecutando ruff..."
"$PYTHON_BIN" -m ruff check src tests

echo "[4/5] Verificando sintaxis frontend..."
npm run -s check:main

echo "[5/5] Verificando formato frontend..."
npx --yes prettier --check "src/frontend/**/*.{js,css,html}"

echo "[5/5] Verificacion completada OK."
