from __future__ import annotations

import json
import os
import shutil
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional


def coerce_backup_bool(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "si", "sí", "yes", "on"}


def perform_backup(
    *,
    reason: str = "manual",
    ensure_backup_dir: Callable[[], None],
    backup_dir: str,
    bogota_tz: Any,
    get_db_conn: Callable[[], Any],
    normalize_snapshot_rows: Callable[[List[Dict[str, Any]]], List[Dict[str, Any]]],
    serialize_product_row: Callable[[Dict[str, Any]], Dict[str, Any]],
    backup_sales_limit: int,
    coerce_decimal: Callable[[Any], Any],
    backup_movements_limit: int,
    offline_cache: Any,
    prune_old_backups: Callable[[], None],
) -> Optional[str]:
    ensure_backup_dir()
    timestamp = datetime.now(bogota_tz).strftime("%Y%m%d-%H%M%S")
    snapshot_path = os.path.join(backup_dir, f"snapshot-{timestamp}.json")
    payload: Dict[str, Any] = {
        "version": 1,
        "created_at": datetime.now(bogota_tz).isoformat(),
        "reason": reason,
        "source": "mysql",
        "metadata": {},
    }
    conn = None
    try:
        conn = get_db_conn()
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT
                id,
                nombre,
                categoria,
                precio,
                iva_percent,
                stock,
                min_stock,
                activo,
                imagen_mime,
                REPLACE(TO_BASE64(imagen_blob), '\n', '') AS imagen_b64
            FROM productos
            ORDER BY id
            """
        )
        productos_raw = normalize_snapshot_rows(cur.fetchall() or [])
        productos: List[Dict[str, Any]] = []
        for row in productos_raw:
            productos.append(serialize_product_row(row))
        payload["productos"] = productos
        cur.execute(
            """
            SELECT
                v.id,
                v.fecha,
                v.usuario_id,
                v.total,
                v.metodo_pago,
                v.iva_percent,
                COALESCE(v.anulada, 0) AS anulada,
                v.anulada_en,
                v.anulada_por,
                v.anulacion_motivo,
                COALESCE(v.anulacion_autorizada, 0) AS anulacion_autorizada,
                v.anulacion_autorizada_en,
                v.anulacion_autorizada_por,
                u.username AS vendedor
            FROM ventas v
            LEFT JOIN usuarios u ON u.id = v.usuario_id
            ORDER BY v.fecha DESC
            LIMIT %s
            """,
            (backup_sales_limit,),
        )
        ventas = normalize_snapshot_rows(cur.fetchall() or [])
        payload["ventas"] = ventas
        venta_ids = [row["id"] for row in ventas if row.get("id") is not None]
        detalles: List[Dict[str, Any]] = []
        if venta_ids:
            placeholders = ",".join(["%s"] * len(venta_ids))
            cur.execute(
                f"""
                SELECT
                    vd.id,
                    vd.venta_id,
                    vd.producto_id,
                    p.nombre AS producto,
                    vd.cantidad,
                    vd.precio,
                    vd.iva_percent
                FROM venta_detalle vd
                LEFT JOIN productos p ON p.id = vd.producto_id
                WHERE vd.venta_id IN ({placeholders})
                """,
                venta_ids,
            )
            detalles = normalize_snapshot_rows(cur.fetchall() or [])
            for row in detalles:
                qty = coerce_decimal(row.get("cantidad") or 0)
                price = coerce_decimal(row.get("precio") or 0.0)
                row["total"] = float(qty) * float(price)
        cur.execute(
            """
            SELECT config_key, config_value, updated_at
            FROM configuracion_app
            ORDER BY config_key
            """
        )
        configuracion = normalize_snapshot_rows(cur.fetchall() or [])
        movement_limit = max(backup_movements_limit, 1)
        cur.execute(
            """
            SELECT
                m.id,
                m.producto_id,
                p.nombre AS producto_nombre,
                m.tipo,
                m.cantidad,
                m.stock_anterior,
                m.stock_nuevo,
                m.motivo,
                m.usuario_id,
                u.username AS usuario,
                m.creado_en
            FROM inventario_movimientos m
            LEFT JOIN productos p ON p.id = m.producto_id
            LEFT JOIN usuarios u ON u.id = m.usuario_id
            ORDER BY m.id DESC
            LIMIT %s
            """,
            (movement_limit,),
        )
        movimientos = normalize_snapshot_rows(cur.fetchall() or [])
        payload["venta_detalle"] = detalles
        payload["configuracion"] = configuracion
        payload["inventario_movimientos"] = movimientos
        payload["metadata"]["productos"] = len(productos)
        payload["metadata"]["ventas"] = len(ventas)
        payload["metadata"]["detalle"] = len(detalles)
        payload["metadata"]["configuracion"] = len(configuracion)
        payload["metadata"]["inventario_movimientos"] = len(movimientos)
    except Exception as exc:
        offline_cache.mark_offline(f"backup error: {exc}")
        print(f"[backup] no se pudo generar respaldo: {exc}")
        return None
    finally:
        if conn:
            conn.close()
    tmp_path = snapshot_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    os.replace(tmp_path, snapshot_path)
    latest_path = os.path.join(backup_dir, "latest.json")
    shutil.copyfile(snapshot_path, latest_path)
    offline_cache.update(payload, source="backup", path=snapshot_path)
    offline_cache.mark_online()
    prune_old_backups()
    print(f"[backup] respaldo almacenado en {snapshot_path}")
    return snapshot_path


def restore_backup_snapshot(
    snapshot_path: str,
    *,
    actor_user_id: Optional[int] = None,
    actor_username: Optional[str] = None,
    load_backup_payload: Callable[[str], Dict[str, Any]],
    get_db_conn: Callable[[], Any],
    ensure_runtime_schema: Callable[..., bool],
    parse_product_image_data_url: Callable[[Any], Any],
    default_iva_percent: Any,
    coerce_backup_bool: Callable[[Any, bool], bool],
    record_audit_event: Callable[..., Any],
    offline_cache: Any,
    bogota_tz: Any,
) -> Dict[str, Any]:
    payload = load_backup_payload(snapshot_path)
    productos = payload.get("productos") or []
    ventas = payload.get("ventas") or []
    detalle = payload.get("venta_detalle") or []
    configuracion = payload.get("configuracion") or []
    movimientos = payload.get("inventario_movimientos") or []
    conn = get_db_conn()
    try:
        ensure_runtime_schema(conn, force=True)
        cur = conn.cursor(dictionary=True)
        conn.start_transaction()
        cur.execute("SET FOREIGN_KEY_CHECKS=0")
        try:
            cur.execute("DELETE FROM inventario_movimientos")
            cur.execute("DELETE FROM venta_detalle")
            cur.execute("DELETE FROM ventas")
            cur.execute("DELETE FROM productos")
            cur.execute("DELETE FROM configuracion_app")
            for row in productos:
                try:
                    image_blob, image_mime, _ = parse_product_image_data_url(
                        row.get("imagen_url") or None
                    )
                except ValueError:
                    image_blob, image_mime = None, None
                cur.execute(
                    """
                    INSERT INTO productos (
                        id, nombre, categoria, precio, iva_percent, stock, min_stock, activo, imagen_blob, imagen_mime
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        int(row.get("id") or 0),
                        (row.get("nombre") or "").strip(),
                        (row.get("categoria") or "").strip() or None,
                        float(row.get("precio") or row.get("precio_base") or 0.0),
                        float(
                            row.get("iva_percent")
                            or row.get("iva_porcentaje")
                            or default_iva_percent
                        ),
                        int(row.get("stock") or 0),
                        int(row.get("min_stock") or 0),
                        1 if coerce_backup_bool(row.get("activo"), True) else 0,
                        image_blob,
                        image_mime,
                    ),
                )
            for row in ventas:
                cur.execute(
                    """
                    INSERT INTO ventas (
                        id, fecha, usuario_id, metodo_pago, total, iva_percent,
                        anulada, anulada_en, anulada_por, anulacion_motivo,
                        anulacion_autorizada, anulacion_autorizada_en, anulacion_autorizada_por
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        int(row.get("id") or 0),
                        row.get("fecha"),
                        row.get("usuario_id"),
                        (row.get("metodo_pago") or "").strip() or None,
                        float(row.get("total") or 0.0),
                        float(row.get("iva_percent") or 0.0),
                        1 if coerce_backup_bool(row.get("anulada"), False) else 0,
                        row.get("anulada_en"),
                        row.get("anulada_por"),
                        (row.get("anulacion_motivo") or "").strip()[:255] or None,
                        1
                        if coerce_backup_bool(
                            row.get("anulacion_autorizada"), False
                        )
                        else 0,
                        row.get("anulacion_autorizada_en"),
                        row.get("anulacion_autorizada_por"),
                    ),
                )
            for row in detalle:
                cur.execute(
                    """
                    INSERT INTO venta_detalle (id, venta_id, producto_id, cantidad, precio, iva_percent)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        int(row.get("id") or 0),
                        int(row.get("venta_id") or 0),
                        int(row.get("producto_id") or 0),
                        int(row.get("cantidad") or 0),
                        float(row.get("precio") or 0.0),
                        float(row.get("iva_percent") or 0.0),
                    ),
                )
            for row in configuracion:
                cur.execute(
                    """
                    INSERT INTO configuracion_app (config_key, config_value, updated_at)
                    VALUES (%s, %s, CURRENT_TIMESTAMP)
                    ON DUPLICATE KEY UPDATE
                        config_value=VALUES(config_value),
                        updated_at=CURRENT_TIMESTAMP
                    """,
                    (
                        (row.get("config_key") or "").strip(),
                        (row.get("config_value") or "").strip(),
                    ),
                )
            for row in reversed(movimientos):
                product_id = row.get("producto_id")
                if not product_id:
                    continue
                cur.execute(
                    """
                    INSERT INTO inventario_movimientos (
                        id, producto_id, tipo, cantidad, stock_anterior, stock_nuevo, motivo, usuario_id, creado_en
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        int(row.get("id") or 0),
                        int(product_id),
                        (row.get("tipo") or "ajuste").strip().lower(),
                        int(row.get("cantidad") or 0),
                        int(row.get("stock_anterior") or 0),
                        int(row.get("stock_nuevo") or 0),
                        (row.get("motivo") or "").strip()[:255] or None,
                        row.get("usuario_id"),
                        row.get("creado_en"),
                    ),
                )
            record_audit_event(
                cur,
                event_type="respaldo_restaurado",
                entity_type="sistema",
                entity_id=None,
                description=f'Respaldo restaurado desde "{os.path.basename(snapshot_path)}"',
                details={
                    "json_filename": os.path.basename(snapshot_path),
                    "created_at": payload.get("created_at"),
                    "metadata": payload.get("metadata") or {},
                },
                actor_user_id=actor_user_id,
                actor_username=actor_username,
            )
            cur.execute("SET FOREIGN_KEY_CHECKS=1")
            conn.commit()
            offline_cache.update(payload, source="backup-restore", path=snapshot_path)
            offline_cache.mark_online()
            return {
                "success": True,
                "json_filename": os.path.basename(snapshot_path),
                "restored_at": datetime.now(bogota_tz).isoformat(),
                "metadata": payload.get("metadata") or {},
            }
        except Exception:
            cur.execute("SET FOREIGN_KEY_CHECKS=1")
            raise
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()
