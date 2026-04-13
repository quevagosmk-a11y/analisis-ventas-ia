#!/bin/sh
set -e

python - <<'PY'
import os
import sys
import time
from urllib.parse import unquote, urlparse

import pymysql


def read_non_empty(*keys, default=None):
    for key in keys:
        value = os.getenv(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return default


def read_allow_empty(*keys, default=None):
    for key in keys:
        if key in os.environ:
            value = os.getenv(key)
            if value is None:
                continue
            return str(value)
    return default


def parse_url(raw_url):
    url = str(raw_url or "").strip()
    if not url:
        return {}
    parsed = urlparse(url)
    scheme = (parsed.scheme or "").split("+", 1)[0].lower()
    if scheme not in {"mysql", "mariadb"}:
        return {}
    return {
        "host": parsed.hostname or None,
        "port": parsed.port or 3306,
        "user": unquote(parsed.username) if parsed.username else None,
        "password": unquote(parsed.password) if parsed.password else None,
        "database": unquote((parsed.path or "").lstrip("/")).strip() or None,
    }


url_config = parse_url(read_non_empty("DB_URL", "DATABASE_URL", "MYSQL_URL"))
host = read_non_empty("DB_HOST", "MYSQLHOST", default=url_config.get("host") or "127.0.0.1")
port = int(read_non_empty("DB_PORT", "MYSQLPORT", default=str(url_config.get("port") or "3306")))
user = read_non_empty("DB_USER", "MYSQLUSER", default=url_config.get("user") or "root")
password = read_allow_empty("DB_PASSWORD", "MYSQLPASSWORD", default=url_config.get("password") or "")
database = read_non_empty("DB_NAME", "MYSQLDATABASE", default=url_config.get("database") or "la_septima_estrella")

timeout_seconds = 120
deadline = time.time() + timeout_seconds

print(f"[entrypoint] Esperando MySQL en {host}:{port}/{database}...")

while time.time() < deadline:
    try:
        conn = pymysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
            connect_timeout=3,
            charset="utf8mb4",
        )
        conn.close()
        print("[entrypoint] MySQL disponible.")
        break
    except Exception as exc:
        print(f"[entrypoint] Esperando DB: {exc}")
        time.sleep(2)
else:
    print("[entrypoint] Timeout esperando MySQL.", file=sys.stderr)
    sys.exit(1)
PY

echo "[entrypoint] Ejecutando bootstrap de tablas/usuarios..."
python src/main.py bootstrap

echo "[entrypoint] Iniciando aplicacion..."
exec python src/main.py
