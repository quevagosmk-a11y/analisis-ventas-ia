#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env.vps"
ENV_EXAMPLE="${ROOT_DIR}/.env.vps.example"
COMPOSE_FILE="${ROOT_DIR}/docker-compose.vps.yml"

if ! command -v docker >/dev/null 2>&1; then
  echo "[deploy] Docker no está instalado en este servidor." >&2
  exit 1
fi

if [ ! -f "${ENV_FILE}" ]; then
  cp "${ENV_EXAMPLE}" "${ENV_FILE}"
  echo "[deploy] Se creó ${ENV_FILE}. Edita las claves antes de continuar." >&2
  exit 1
fi

mkdir -p "${ROOT_DIR}/backups" "${ROOT_DIR}/deploy/vps/mysql-init"

docker compose \
  --env-file "${ENV_FILE}" \
  -f "${COMPOSE_FILE}" \
  up -d --build

echo "[deploy] Stack VPS levantado."
echo "[deploy] URL esperada: http://$(hostname -I | awk '{print $1}')"
