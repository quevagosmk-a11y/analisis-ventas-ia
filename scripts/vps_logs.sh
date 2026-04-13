#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env.vps"
COMPOSE_FILE="${ROOT_DIR}/docker-compose.vps.yml"

docker compose \
  --env-file "${ENV_FILE}" \
  -f "${COMPOSE_FILE}" \
  logs -f "${@:-app mysql}"
