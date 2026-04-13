#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_FILE="${1:-${ROOT_DIR}/deploy/vps/mysql-init/01-beta.sql}"

mkdir -p "$(dirname "${OUT_FILE}")"

if [ ! -f "${ROOT_DIR}/.env" ]; then
  echo "[dump] Falta ${ROOT_DIR}/.env" >&2
  exit 1
fi

set -a
. "${ROOT_DIR}/.env"
set +a

DB_HOST="${DB_HOST:-127.0.0.1}"
DB_PORT="${DB_PORT:-3306}"
DB_USER="${DB_USER:-root}"
DB_NAME="${DB_NAME:-la_septima_estrella}"
DB_PASSWORD="${DB_PASSWORD:-}"

if ! command -v mysqldump >/dev/null 2>&1; then
  echo "[dump] mysqldump no está disponible en este equipo." >&2
  echo "[dump] Instala MySQL client o exporta el dump manualmente." >&2
  exit 1
fi

MYSQL_PWD="${DB_PASSWORD}" mysqldump \
  -h "${DB_HOST}" \
  -P "${DB_PORT}" \
  -u "${DB_USER}" \
  --databases "${DB_NAME}" \
  --routines \
  --triggers \
  --single-transaction \
  > "${OUT_FILE}"

echo "[dump] Exportado en ${OUT_FILE}"
