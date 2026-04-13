from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

SQL_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9_]+$")


def _scalar_row_value(row: Any, key: str = "valor") -> Any:
    if isinstance(row, dict):
        return row.get(key)
    if isinstance(row, (tuple, list)) and row:
        return row[0]
    return None


def _safe_sql_identifier(name: str) -> str:
    normalized = str(name or "").strip()
    if not SQL_IDENTIFIER_PATTERN.match(normalized):
        raise ValueError(f"Identificador SQL invalido: {name!r}")
    return normalized


def table_exists(cur, table_name: str) -> bool:
    table = _safe_sql_identifier(table_name)
    cur.execute("SHOW TABLES LIKE %s", (table,))
    return cur.fetchone() is not None


def column_exists(cur, table_name: str, column_name: str) -> bool:
    table = _safe_sql_identifier(table_name)
    column = _safe_sql_identifier(column_name)
    cur.execute(f"SHOW COLUMNS FROM `{table}` LIKE %s", (column,))
    return cur.fetchone() is not None


def index_exists(cur, table_name: str, index_name: str) -> bool:
    table = _safe_sql_identifier(table_name)
    index = _safe_sql_identifier(index_name)
    cur.execute(f"SHOW INDEX FROM `{table}` WHERE Key_name=%s", (index,))
    return cur.fetchone() is not None


def add_column_if_missing(
    cur, table_name: str, column_name: str, column_sql: str
) -> bool:
    table = _safe_sql_identifier(table_name)
    column = _safe_sql_identifier(column_name)
    if not table_exists(cur, table) or column_exists(cur, table, column):
        return False
    cur.execute(f"ALTER TABLE `{table}` ADD COLUMN {column_sql}")
    return True


def add_index_if_missing(cur, table_name: str, index_name: str, index_sql: str) -> bool:
    table = _safe_sql_identifier(table_name)
    index = _safe_sql_identifier(index_name)
    if not table_exists(cur, table) or index_exists(cur, table, index):
        return False
    cur.execute(f"ALTER TABLE `{table}` ADD {index_sql}")
    return True


def get_table_engine(cur, table_name: str) -> Optional[str]:
    table = _safe_sql_identifier(table_name)
    if not table_exists(cur, table):
        return None
    cur.execute(
        """
        SELECT ENGINE
        FROM information_schema.TABLES
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
        LIMIT 1
        """,
        (table,),
    )
    row = cur.fetchone()
    return str(_scalar_row_value(row, "ENGINE") or "").strip() or None


def ensure_table_engine_innodb(cur, table_name: str) -> bool:
    table = _safe_sql_identifier(table_name)
    engine = get_table_engine(cur, table)
    if not engine:
        return False
    if engine.lower() == "innodb":
        return False
    cur.execute(f"ALTER TABLE `{table}` ENGINE=InnoDB")
    return True


def foreign_key_exists(cur, table_name: str, fk_name: str) -> bool:
    table = _safe_sql_identifier(table_name)
    fk = _safe_sql_identifier(fk_name)
    cur.execute(
        """
        SELECT 1
        FROM information_schema.TABLE_CONSTRAINTS
        WHERE CONSTRAINT_SCHEMA = DATABASE()
          AND TABLE_NAME = %s
          AND CONSTRAINT_NAME = %s
          AND CONSTRAINT_TYPE = 'FOREIGN KEY'
        LIMIT 1
        """,
        (table, fk),
    )
    return cur.fetchone() is not None


def foreign_key_for_column_exists(cur, table_name: str, column_name: str) -> bool:
    table = _safe_sql_identifier(table_name)
    column = _safe_sql_identifier(column_name)
    cur.execute(
        """
        SELECT 1
        FROM information_schema.KEY_COLUMN_USAGE
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = %s
          AND COLUMN_NAME = %s
          AND REFERENCED_TABLE_NAME IS NOT NULL
        LIMIT 1
        """,
        (table, column),
    )
    return cur.fetchone() is not None


def any_index_for_column_exists(cur, table_name: str, column_name: str) -> bool:
    table = _safe_sql_identifier(table_name)
    column = _safe_sql_identifier(column_name)
    cur.execute(f"SHOW INDEX FROM `{table}` WHERE Column_name=%s", (column,))
    return cur.fetchone() is not None


def add_foreign_key_if_missing(
    cur,
    *,
    table_name: str,
    column_name: str,
    ref_table: str,
    ref_column: str,
    fk_name: str,
    on_delete: str = "RESTRICT",
    on_update: str = "CASCADE",
) -> bool:
    table = _safe_sql_identifier(table_name)
    column = _safe_sql_identifier(column_name)
    parent_table = _safe_sql_identifier(ref_table)
    parent_column = _safe_sql_identifier(ref_column)
    fk = _safe_sql_identifier(fk_name)
    if not table_exists(cur, table) or not table_exists(cur, parent_table):
        return False
    if not column_exists(cur, table, column) or not column_exists(
        cur, parent_table, parent_column
    ):
        return False
    if foreign_key_exists(cur, table, fk) or foreign_key_for_column_exists(
        cur, table, column
    ):
        return False
    if not any_index_for_column_exists(cur, table, column):
        add_index_if_missing(
            cur,
            table,
            f"idx_{table}_{column}",
            f"INDEX `idx_{table}_{column}` (`{column}`)",
        )

    safe_actions = {"RESTRICT", "CASCADE", "SET NULL", "NO ACTION"}
    delete_action = str(on_delete or "RESTRICT").strip().upper()
    update_action = str(on_update or "CASCADE").strip().upper()
    if delete_action not in safe_actions:
        delete_action = "RESTRICT"
    if update_action not in safe_actions:
        update_action = "CASCADE"
    cur.execute(
        f"""
        ALTER TABLE `{table}`
        ADD CONSTRAINT `{fk}`
        FOREIGN KEY (`{column}`)
        REFERENCES `{parent_table}` (`{parent_column}`)
        ON DELETE {delete_action}
        ON UPDATE {update_action}
        """
    )
    return True


def count_orphan_references(
    cur, table_name: str, column_name: str, ref_table: str, ref_column: str = "id"
) -> int:
    table = _safe_sql_identifier(table_name)
    column = _safe_sql_identifier(column_name)
    parent_table = _safe_sql_identifier(ref_table)
    parent_column = _safe_sql_identifier(ref_column)
    if not table_exists(cur, table) or not table_exists(cur, parent_table):
        return 0
    cur.execute(
        f"""
        SELECT COUNT(*) AS total
        FROM `{table}` c
        LEFT JOIN `{parent_table}` p
          ON c.`{column}` = p.`{parent_column}`
        WHERE c.`{column}` IS NOT NULL
          AND p.`{parent_column}` IS NULL
        """
    )
    row = cur.fetchone()
    return int(_scalar_row_value(row, "total") or 0)


def nullify_orphan_references(
    cur, table_name: str, column_name: str, ref_table: str, ref_column: str = "id"
) -> int:
    table = _safe_sql_identifier(table_name)
    column = _safe_sql_identifier(column_name)
    parent_table = _safe_sql_identifier(ref_table)
    parent_column = _safe_sql_identifier(ref_column)
    if not table_exists(cur, table) or not table_exists(cur, parent_table):
        return 0
    cur.execute(
        f"""
        UPDATE `{table}` c
        LEFT JOIN `{parent_table}` p
          ON c.`{column}` = p.`{parent_column}`
        SET c.`{column}` = NULL
        WHERE c.`{column}` IS NOT NULL
          AND p.`{parent_column}` IS NULL
        """
    )
    return int(getattr(cur, "rowcount", 0) or 0)


def migrate_foreign_keys(cur) -> Dict[str, int]:
    stats = {
        "tables_converted_to_innodb": 0,
        "foreign_keys_added": 0,
        "foreign_keys_skipped": 0,
        "orphan_rows_nullified": 0,
    }
    related_tables = (
        "usuarios",
        "productos",
        "ventas",
        "venta_detalle",
        "sesiones_activas",
        "inventario_movimientos",
        "producto_precio_auditoria",
        "auditoria_eventos",
        "venta_recomendaciones",
    )
    for table in related_tables:
        try:
            if ensure_table_engine_innodb(cur, table):
                stats["tables_converted_to_innodb"] += 1
        except Exception as exc:
            print(f"[schema] aviso: no se pudo convertir `{table}` a InnoDB: {exc}")

    fk_specs: List[Dict[str, Any]] = [
        {
            "table": "ventas",
            "column": "usuario_id",
            "ref_table": "usuarios",
            "fk_name": "fk_ventas_usuario",
            "nullable": True,
            "on_delete": "SET NULL",
        },
        {
            "table": "ventas",
            "column": "anulada_por",
            "ref_table": "usuarios",
            "fk_name": "fk_ventas_anulada_por",
            "nullable": True,
            "on_delete": "SET NULL",
        },
        {
            "table": "ventas",
            "column": "anulacion_autorizada_por",
            "ref_table": "usuarios",
            "fk_name": "fk_ventas_anulacion_autorizada_por",
            "nullable": True,
            "on_delete": "SET NULL",
        },
        {
            "table": "venta_detalle",
            "column": "venta_id",
            "ref_table": "ventas",
            "fk_name": "fk_venta_detalle_venta",
            "nullable": False,
            "on_delete": "RESTRICT",
        },
        {
            "table": "venta_detalle",
            "column": "producto_id",
            "ref_table": "productos",
            "fk_name": "fk_venta_detalle_producto",
            "nullable": False,
            "on_delete": "RESTRICT",
        },
        {
            "table": "sesiones_activas",
            "column": "user_id",
            "ref_table": "usuarios",
            "fk_name": "fk_sesiones_usuario",
            "nullable": False,
            "on_delete": "RESTRICT",
        },
        {
            "table": "inventario_movimientos",
            "column": "producto_id",
            "ref_table": "productos",
            "fk_name": "fk_inventario_producto",
            "nullable": False,
            "on_delete": "RESTRICT",
        },
        {
            "table": "inventario_movimientos",
            "column": "usuario_id",
            "ref_table": "usuarios",
            "fk_name": "fk_inventario_usuario",
            "nullable": True,
            "on_delete": "SET NULL",
        },
        {
            "table": "producto_precio_auditoria",
            "column": "producto_id",
            "ref_table": "productos",
            "fk_name": "fk_precio_auditoria_producto",
            "nullable": False,
            "on_delete": "RESTRICT",
        },
        {
            "table": "producto_precio_auditoria",
            "column": "usuario_id",
            "ref_table": "usuarios",
            "fk_name": "fk_precio_auditoria_usuario",
            "nullable": True,
            "on_delete": "SET NULL",
        },
        {
            "table": "auditoria_eventos",
            "column": "actor_user_id",
            "ref_table": "usuarios",
            "fk_name": "fk_auditoria_actor",
            "nullable": True,
            "on_delete": "SET NULL",
        },
        {
            "table": "venta_recomendaciones",
            "column": "venta_id",
            "ref_table": "ventas",
            "fk_name": "fk_recomendacion_venta",
            "nullable": False,
            "on_delete": "CASCADE",
        },
    ]

    for spec in fk_specs:
        table_name = str(spec.get("table") or "")
        column_name = str(spec.get("column") or "")
        ref_table = str(spec.get("ref_table") or "")
        fk_name = str(spec.get("fk_name") or "")
        nullable = bool(spec.get("nullable"))
        try:
            if nullable:
                stats["orphan_rows_nullified"] += nullify_orphan_references(
                    cur,
                    table_name,
                    column_name,
                    ref_table,
                    "id",
                )
            orphan_count = count_orphan_references(
                cur, table_name, column_name, ref_table, "id"
            )
            if orphan_count > 0:
                stats["foreign_keys_skipped"] += 1
                print(
                    f"[schema] aviso: FK `{fk_name}` omitida por {orphan_count} referencias huerfanas en "
                    f"`{table_name}`.`{column_name}`"
                )
                continue
            if add_foreign_key_if_missing(
                cur,
                table_name=table_name,
                column_name=column_name,
                ref_table=ref_table,
                ref_column="id",
                fk_name=fk_name,
                on_delete=str(spec.get("on_delete") or "RESTRICT"),
                on_update="CASCADE",
            ):
                stats["foreign_keys_added"] += 1
        except Exception as exc:
            stats["foreign_keys_skipped"] += 1
            print(f"[schema] aviso: no se pudo crear FK `{fk_name}`: {exc}")
    return stats


def is_unknown_column_error(exc: Exception, column_name: str) -> bool:
    message = str(exc or "").lower()
    return "unknown column" in message and str(column_name or "").lower() in message


def products_active_column_available(cur) -> bool:
    try:
        return column_exists(cur, "productos", "activo")
    except Exception:
        return False


def build_active_product_condition(cur, alias: Optional[str] = None) -> str:
    if not products_active_column_available(cur):
        return "1=1"
    prefix = f"{alias}." if alias else ""
    return f"{prefix}activo=1"


def migrate_legacy_schema(cur) -> Dict[str, int]:
    column_specs: Dict[str, List[Tuple[str, str]]] = {
        "usuarios": [
            ("name", "`name` VARCHAR(128) NULL"),
            ("role", "`role` VARCHAR(32) DEFAULT 'vendedor'"),
            ("activo", "`activo` TINYINT(1) NOT NULL DEFAULT 1"),
            ("creado_en", "`creado_en` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP"),
        ],
        "productos": [
            ("categoria", "`categoria` VARCHAR(128) NULL"),
            ("precio", "`precio` DECIMAL(12,2) NOT NULL DEFAULT 0.00"),
            ("iva_percent", "`iva_percent` DECIMAL(5,2) NOT NULL DEFAULT 19.00"),
            ("stock", "`stock` INT NOT NULL DEFAULT 0"),
            ("min_stock", "`min_stock` INT NOT NULL DEFAULT 0"),
            ("imagen_blob", "`imagen_blob` LONGBLOB NULL"),
            ("imagen_mime", "`imagen_mime` VARCHAR(64) NULL"),
            ("activo", "`activo` TINYINT(1) NOT NULL DEFAULT 1"),
            ("creado_en", "`creado_en` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP"),
        ],
        "ventas": [
            ("fecha", "`fecha` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP"),
            ("usuario_id", "`usuario_id` INT NULL"),
            ("metodo_pago", "`metodo_pago` VARCHAR(32) NULL"),
            ("iva_percent", "`iva_percent` DECIMAL(5,2) NOT NULL DEFAULT 19.00"),
            ("total", "`total` DECIMAL(12,2) NOT NULL DEFAULT 0.00"),
        ],
        "venta_detalle": [
            ("venta_id", "`venta_id` INT NOT NULL"),
            ("producto_id", "`producto_id` INT NOT NULL"),
            ("cantidad", "`cantidad` INT NOT NULL"),
            ("precio", "`precio` DECIMAL(12,2) NOT NULL DEFAULT 0.00"),
            ("iva_percent", "`iva_percent` DECIMAL(5,2) NOT NULL DEFAULT 19.00"),
        ],
        "producto_precio_auditoria": [
            ("producto_id", "`producto_id` INT NOT NULL"),
            ("usuario_id", "`usuario_id` INT NULL"),
            (
                "precio_anterior",
                "`precio_anterior` DECIMAL(12,2) NOT NULL DEFAULT 0.00",
            ),
            ("precio_nuevo", "`precio_nuevo` DECIMAL(12,2) NOT NULL DEFAULT 0.00"),
            ("motivo", "`motivo` VARCHAR(255) NULL"),
            ("creado_en", "`creado_en` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP"),
        ],
        "inventario_movimientos": [
            ("producto_id", "`producto_id` INT NOT NULL"),
            ("tipo", "`tipo` VARCHAR(16) NOT NULL"),
            ("cantidad", "`cantidad` INT NOT NULL"),
            ("stock_anterior", "`stock_anterior` INT NOT NULL DEFAULT 0"),
            ("stock_nuevo", "`stock_nuevo` INT NOT NULL DEFAULT 0"),
            ("motivo", "`motivo` VARCHAR(255) NULL"),
            ("usuario_id", "`usuario_id` INT NULL"),
            ("creado_en", "`creado_en` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP"),
        ],
        "sesiones_activas": [
            ("user_id", "`user_id` INT NOT NULL"),
            ("role", "`role` VARCHAR(32) NULL"),
            ("created_at", "`created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP"),
            (
                "last_activity",
                "`last_activity` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP",
            ),
            ("expires_at", "`expires_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP"),
            ("revoked", "`revoked` TINYINT(1) NOT NULL DEFAULT 0"),
            ("client_info", "`client_info` VARCHAR(255) NULL"),
        ],
        "tabla_logs_ia": [
            ("fecha_ejecucion", "`fecha_ejecucion` DATETIME NOT NULL"),
            ("payload_json", "`payload_json` LONGTEXT NOT NULL"),
            ("fuente", "`fuente` VARCHAR(64) NULL"),
            ("version", "`version` VARCHAR(32) NULL"),
            ("creado_en", "`creado_en` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP"),
        ],
        "auditoria_eventos": [
            ("event_type", "`event_type` VARCHAR(64) NOT NULL"),
            ("entity_type", "`entity_type` VARCHAR(32) NULL"),
            ("entity_id", "`entity_id` INT NULL"),
            ("description", "`description` VARCHAR(255) NOT NULL"),
            ("details_json", "`details_json` LONGTEXT NULL"),
            ("actor_user_id", "`actor_user_id` INT NULL"),
            ("actor_username", "`actor_username` VARCHAR(64) NULL"),
            ("created_at", "`created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP"),
        ],
    }
    index_specs: Dict[str, List[Tuple[str, str]]] = {
        "productos": [("idx_activo", "INDEX `idx_activo` (`activo`)")],
        "ventas": [
            ("idx_fecha", "INDEX `idx_fecha` (`fecha`)"),
            ("idx_usuario_id", "INDEX `idx_usuario_id` (`usuario_id`)"),
        ],
        "venta_detalle": [
            ("idx_venta", "INDEX `idx_venta` (`venta_id`)"),
            ("idx_producto", "INDEX `idx_producto` (`producto_id`)"),
        ],
        "producto_precio_auditoria": [
            ("idx_producto", "INDEX `idx_producto` (`producto_id`)"),
            ("idx_usuario_id", "INDEX `idx_usuario_id` (`usuario_id`)"),
        ],
        "inventario_movimientos": [
            ("idx_producto", "INDEX `idx_producto` (`producto_id`)"),
            ("idx_creado", "INDEX `idx_creado` (`creado_en`)"),
            ("idx_usuario_id", "INDEX `idx_usuario_id` (`usuario_id`)"),
        ],
        "sesiones_activas": [("idx_user_id", "INDEX `idx_user_id` (`user_id`)")],
        "venta_recomendaciones": [
            ("idx_venta_id", "INDEX `idx_venta_id` (`venta_id`)")
        ],
        "tabla_logs_ia": [
            ("idx_fecha_ejecucion", "INDEX `idx_fecha_ejecucion` (`fecha_ejecucion`)")
        ],
        "auditoria_eventos": [
            ("idx_audit_created", "INDEX `idx_audit_created` (`created_at`)"),
            ("idx_audit_event", "INDEX `idx_audit_event` (`event_type`, `created_at`)"),
            (
                "idx_audit_actor",
                "INDEX `idx_audit_actor` (`actor_user_id`, `created_at`)",
            ),
        ],
    }
    stats = {"columns_added": 0, "indexes_added": 0}
    for table_name, specs in column_specs.items():
        for column_name, ddl in specs:
            if add_column_if_missing(cur, table_name, column_name, ddl):
                stats["columns_added"] += 1
    for table_name, specs in index_specs.items():
        for index_name, ddl in specs:
            if add_index_if_missing(cur, table_name, index_name, ddl):
                stats["indexes_added"] += 1
    return stats
