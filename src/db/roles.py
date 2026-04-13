from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional

SYSTEM_USER_ROLES = ("admin", "gerente", "vendedor", "auditador")
ROLE_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]{2,31}$")
ROLE_PERMISSION_KEYS = (
    "dashboard_view",
    "sales_view",
    "sales_create",
    "products_view",
    "products_manage",
    "reports_view",
    "statistics_view",
    "users_manage",
    "audit_view",
    "sessions_manage",
    "backups_manage",
    "ai_chat",
)
ROLE_PERMISSION_LABELS = {
    "dashboard_view": "Ver dashboard",
    "sales_view": "Ver ventas",
    "sales_create": "Registrar ventas",
    "products_view": "Ver productos",
    "products_manage": "Gestionar productos",
    "reports_view": "Ver reportes",
    "statistics_view": "Ver estadisticas",
    "users_manage": "Gestionar usuarios",
    "audit_view": "Ver auditoria",
    "sessions_manage": "Gestionar sesiones",
    "backups_manage": "Gestionar respaldos",
    "ai_chat": "Usar asistente IA",
}


def default_role_permissions(role: Optional[str]) -> Dict[str, bool]:
    normalized = (role or "").strip().lower()
    if normalized == "admin":
        return {key: True for key in ROLE_PERMISSION_KEYS}
    base = {key: False for key in ROLE_PERMISSION_KEYS}
    if normalized == "gerente":
        for key in (
            "dashboard_view",
            "sales_view",
            "sales_create",
            "products_view",
            "products_manage",
            "users_manage",
            "backups_manage",
            "reports_view",
            "statistics_view",
            "ai_chat",
        ):
            base[key] = True
        base["sessions_manage"] = False
        return base
    if normalized == "auditador":
        base["audit_view"] = True
        return base
    if normalized == "vendedor":
        for key in (
            "dashboard_view",
            "sales_view",
            "sales_create",
            "products_view",
            "ai_chat",
        ):
            base[key] = True
    return base


def normalize_permissions_map(
    raw_permissions: Any, *, role: Optional[str] = None
) -> Dict[str, bool]:
    permissions = default_role_permissions(role)
    if isinstance(raw_permissions, dict):
        for key in ROLE_PERMISSION_KEYS:
            if key in raw_permissions:
                permissions[key] = bool(raw_permissions.get(key))
    elif isinstance(raw_permissions, (list, tuple, set)):
        selected = {str(item or "").strip() for item in raw_permissions}
        for key in ROLE_PERMISSION_KEYS:
            permissions[key] = key in selected
    if (role or "").strip().lower() == "admin":
        return {key: True for key in ROLE_PERMISSION_KEYS}
    return permissions


def normalize_user_role(raw_value: Any) -> str:
    role = (raw_value or "vendedor").strip().lower()
    if not role:
        role = "vendedor"
    if not ROLE_NAME_PATTERN.match(role):
        raise ValueError(
            "Rol invalido. Usa entre 3 y 32 caracteres con letras, numeros o guion bajo."
        )
    return role


def coerce_user_role(raw_value: Any, default: str = "vendedor") -> str:
    try:
        return normalize_user_role(raw_value)
    except ValueError:
        try:
            return normalize_user_role(default)
        except ValueError:
            return "vendedor"


def role_display_name(role: Any) -> str:
    normalized = coerce_user_role(role)
    if normalized == "admin":
        return "Administrador"
    if normalized == "gerente":
        return "Gerente"
    if normalized == "vendedor":
        return "Vendedor"
    if normalized == "auditador":
        return "Auditador"
    return normalized.replace("_", " ").title()


def count_active_admins(cur) -> int:
    cur.execute(
        "SELECT COUNT(*) AS total FROM usuarios WHERE role='admin' AND activo=1"
    )
    row = cur.fetchone() or {}
    if isinstance(row, dict):
        return int(row.get("total") or 0)
    try:
        return int(row[0] or 0)
    except Exception:
        return 0


def ensure_roles_permissions_table(cur) -> None:
    def _is_missing_in_engine(exc: Exception) -> bool:
        msg = str(exc or "").lower()
        return "roles_permisos" in msg and (
            "doesn't exist in engine" in msg or "doesnt exist in engine" in msg
        )

    def _create_base_table() -> None:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS roles_permisos (
                role VARCHAR(32) PRIMARY KEY,
                name VARCHAR(64) NOT NULL,
                permissions_json LONGTEXT NOT NULL,
                is_system TINYINT(1) NOT NULL DEFAULT 0,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            )
            """
        )

    def _recreate_table() -> None:
        try:
            cur.execute("DROP TABLE IF EXISTS roles_permisos")
        except Exception:
            pass
        _create_base_table()

    try:
        _create_base_table()
    except Exception as exc:
        if _is_missing_in_engine(exc):
            _recreate_table()
        else:
            raise

    def _has_column(column_name: str) -> bool:
        try:
            cur.execute("SHOW COLUMNS FROM roles_permisos LIKE %s", (column_name,))
            return bool(cur.fetchone())
        except Exception as exc:
            if _is_missing_in_engine(exc):
                _recreate_table()
                cur.execute("SHOW COLUMNS FROM roles_permisos LIKE %s", (column_name,))
                return bool(cur.fetchone())
            return False

    if not _has_column("name"):
        cur.execute("ALTER TABLE roles_permisos ADD COLUMN name VARCHAR(64) NULL")
        cur.execute("UPDATE roles_permisos SET name=role WHERE name IS NULL OR name=''")
    if not _has_column("permissions_json"):
        cur.execute(
            "ALTER TABLE roles_permisos ADD COLUMN permissions_json LONGTEXT NULL"
        )
        if _has_column("permissions"):
            cur.execute(
                """
                UPDATE roles_permisos
                SET permissions_json = permissions
                WHERE permissions_json IS NULL AND permissions IS NOT NULL
                """
            )
        cur.execute(
            "UPDATE roles_permisos SET permissions_json='{}' WHERE permissions_json IS NULL"
        )
    if not _has_column("is_system"):
        cur.execute(
            "ALTER TABLE roles_permisos ADD COLUMN is_system TINYINT(1) NOT NULL DEFAULT 0"
        )
    if not _has_column("created_at"):
        cur.execute(
            "ALTER TABLE roles_permisos ADD COLUMN created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP"
        )
    if not _has_column("updated_at"):
        cur.execute(
            "ALTER TABLE roles_permisos ADD COLUMN updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"
        )


def _serialize_permissions(permissions: Dict[str, bool]) -> str:
    normalized = {
        key: bool((permissions or {}).get(key)) for key in ROLE_PERMISSION_KEYS
    }
    return json.dumps(normalized, ensure_ascii=False, sort_keys=True)


def _parse_permissions_json(raw_value: Any, *, role: Optional[str]) -> Dict[str, bool]:
    if not raw_value:
        return default_role_permissions(role)
    try:
        parsed = json.loads(raw_value)
    except (TypeError, ValueError, json.JSONDecodeError):
        parsed = {}
    return normalize_permissions_map(parsed, role=role)


def fetch_role_definition(cur, role: Any) -> Optional[Dict[str, Any]]:
    normalized = coerce_user_role(role)
    ensure_roles_permissions_table(cur)
    cur.execute(
        """
        SELECT role, name, permissions_json, is_system
        FROM roles_permisos
        WHERE role=%s
        LIMIT 1
        """,
        (normalized,),
    )
    row = cur.fetchone()
    if not row:
        return None
    if not isinstance(row, dict):
        return None
    permissions = _parse_permissions_json(row.get("permissions_json"), role=normalized)
    return {
        "role": normalized,
        "name": (row.get("name") or role_display_name(normalized)).strip()
        or role_display_name(normalized),
        "permissions": permissions,
        "is_system": bool(row.get("is_system")),
    }


def save_role_definition(
    cur,
    *,
    role: str,
    name: str,
    permissions: Dict[str, bool],
    is_system: bool = False,
) -> None:
    normalized_role = normalize_user_role(role)
    normalized_name = (
        name or role_display_name(normalized_role)
    ).strip() or role_display_name(normalized_role)
    normalized_permissions = normalize_permissions_map(
        permissions, role=normalized_role
    )
    ensure_roles_permissions_table(cur)
    cur.execute(
        """
        INSERT INTO roles_permisos (role, name, permissions_json, is_system)
        VALUES (%s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            name=VALUES(name),
            permissions_json=VALUES(permissions_json),
            is_system=VALUES(is_system),
            updated_at=CURRENT_TIMESTAMP
        """,
        (
            normalized_role,
            normalized_name[:64],
            _serialize_permissions(normalized_permissions),
            1 if is_system else 0,
        ),
    )


def ensure_default_role_definitions(conn) -> None:
    cur = conn.cursor(dictionary=True)
    try:
        ensure_roles_permissions_table(cur)
        admin_permissions = default_role_permissions("admin")
        save_role_definition(
            cur,
            role="admin",
            name="Administrador",
            permissions=admin_permissions,
            is_system=True,
        )
        manager_permissions = default_role_permissions("gerente")
        save_role_definition(
            cur,
            role="gerente",
            name="Gerente",
            permissions=manager_permissions,
            is_system=True,
        )
        auditor_permissions = default_role_permissions("auditador")
        save_role_definition(
            cur,
            role="auditador",
            name="Auditador",
            permissions=auditor_permissions,
            is_system=True,
        )
        vendor_row = fetch_role_definition(cur, "vendedor")
        if vendor_row:
            vendor_permissions = normalize_permissions_map(
                vendor_row.get("permissions"), role="vendedor"
            )
        else:
            vendor_permissions = default_role_permissions("vendedor")
        vendor_permissions["reports_view"] = False
        save_role_definition(
            cur,
            role="vendedor",
            name="Vendedor",
            permissions=vendor_permissions,
            is_system=True,
        )
        conn.commit()
    finally:
        cur.close()


def resolve_role_permissions(cur, role: Any) -> Dict[str, bool]:
    normalized = coerce_user_role(role)
    role_row = fetch_role_definition(cur, normalized)
    if role_row:
        return normalize_permissions_map(role_row.get("permissions"), role=normalized)
    if normalized in SYSTEM_USER_ROLES:
        return default_role_permissions(normalized)
    return default_role_permissions("vendedor")


def resolve_role_name(cur, role: Any) -> str:
    normalized = coerce_user_role(role)
    role_row = fetch_role_definition(cur, normalized)
    if role_row:
        name = (role_row.get("name") or "").strip()
        if name:
            return name
    return role_display_name(normalized)


def role_exists(cur, role: Any) -> bool:
    normalized = coerce_user_role(role)
    ensure_roles_permissions_table(cur)
    cur.execute("SELECT role FROM roles_permisos WHERE role=%s LIMIT 1", (normalized,))
    return bool(cur.fetchone())
