#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env.vps"
COMPOSE_FILE="${ROOT_DIR}/docker-compose.vps.yml"

if [ ! -f "${ENV_FILE}" ]; then
  echo "[deploy] Falta ${ENV_FILE}" >&2
  exit 1
fi

if [ $# -lt 1 ]; then
  echo "Uso: $0 /ruta/al/beta_dump.sql" >&2
  exit 1
fi

SQL_FILE="$1"
if [ ! -f "${SQL_FILE}" ]; then
  echo "[deploy] No existe el archivo ${SQL_FILE}" >&2
  exit 1
fi

set -a
. "${ENV_FILE}"
set +a

docker compose \
  --env-file "${ENV_FILE}" \
  -f "${COMPOSE_FILE}" \
  exec -T mysql \
  sh -lc 'mysql -uroot -p"$DB_PASSWORD" "$DB_NAME"' < "${SQL_FILE}"

docker compose \
  --env-file "${ENV_FILE}" \
  -f "${COMPOSE_FILE}" \
  restart app

echo "[deploy] Dump importado y aplicación reiniciada."
