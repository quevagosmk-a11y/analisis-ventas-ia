from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    env_path = project_root / ".env"
    env_data: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env_data[key.strip()] = value.strip()

    try:
        import pymysql
    except Exception as exc:  # pragma: no cover - entorno Windows
        raise SystemExit(f"[check] falta PyMySQL: {exc}")

    conn = pymysql.connect(
        host=env_data.get("DB_HOST", "127.0.0.1"),
        port=int(env_data.get("DB_PORT", "3306")),
        user=env_data.get("DB_USER", "root"),
        password=env_data.get("DB_PASSWORD", ""),
        database=env_data.get("DB_NAME", "la_septima_estrella"),
        charset="utf8mb4",
        autocommit=True,
    )
    cur = conn.cursor()
    payload: dict[str, object] = {}
    for table_name in [
        "usuarios",
        "productos",
        "ventas",
        "venta_detalle",
        "inventario_movimientos",
    ]:
        cur.execute(f"SELECT COUNT(*) FROM {table_name}")
        payload[table_name] = int(cur.fetchone()[0])
    cur.execute("SELECT id, username, role, activo FROM usuarios ORDER BY id")
    payload["usuarios_rows"] = cur.fetchall()
    cur.close()
    conn.close()
    result = json.dumps(payload, ensure_ascii=False)
    if len(sys.argv) > 1:
        Path(sys.argv[1]).resolve().write_text(result, encoding="utf-8")
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
