from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

AUDIT_EVENT_TYPE_ALIASES = {
    "producto_desactivado": "producto_estado_actualizado",
    "producto_activado": "producto_estado_actualizado",
    "producto_minimo_actualizado": "minimo_stock_actualizado",
}

AUDIT_ACTION_GROUPS = (
    {
        "producto_estado_actualizado",
        "producto_desactivado",
        "producto_activado",
        "producto_eliminado",
    },
    {"minimo_stock_actualizado", "producto_minimo_actualizado"},
    {"stock_ajustado", "inventario_movimiento"},
)

HIDDEN_AUDIT_EVENT_TYPES = {
    "inventario_exportado",
    "reporte_exportado",
    "estadisticas_exportadas",
    "auditoria_exportada",
}


def normalize_audit_event_type(raw_value: Optional[str]) -> str:
    value = str(raw_value or "").strip().lower()
    if not value:
        return "evento"
    return AUDIT_EVENT_TYPE_ALIASES.get(value, value)


def resolve_audit_action_filter(raw_value: Optional[str]) -> Optional[set[str]]:
    value = normalize_audit_event_type(raw_value)
    if not value or value == "evento":
        return None
    for group in AUDIT_ACTION_GROUPS:
        if value in group:
            return set(group)
    return {value}


def parse_int_limit(
    raw_value: Optional[str],
    *,
    default: int = 400,
    min_value: int = 1,
    max_value: int = 5000,
) -> int:
    try:
        value = int(str(raw_value or "").strip() or default)
    except (TypeError, ValueError):
        return default
    return max(min_value, min(max_value, value))


def parse_json_object(raw_value: Any) -> Dict[str, Any]:
    if isinstance(raw_value, dict):
        return raw_value
    if not raw_value:
        return {}
    try:
        payload = json.loads(raw_value)
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def build_audit_actor_label(entry: Dict[str, Any]) -> str:
    return (
        str(entry.get("actor_name") or "").strip()
        or str(entry.get("actor_username") or "").strip()
        or (
            f'usuario#{int(entry.get("actor_user_id") or 0)}'
            if int(entry.get("actor_user_id") or 0) > 0
            else "Sin registro"
        )
    )


def build_audit_entity_label(entry: Dict[str, Any]) -> str:
    entity_type = str(entry.get("entity_type") or "").strip() or "-"
    entity_id = entry.get("entity_id")
    if entity_id is None:
        return entity_type
    try:
        return f"{entity_type} #{int(entity_id)}"
    except (TypeError, ValueError):
        return entity_type


def serialize_audit_entry(
    row: Dict[str, Any],
    *,
    normalize_event_type: Callable[[Optional[str]], str],
    parse_json_object_fn: Callable[[Any], Dict[str, Any]],
    bogota_isoformat: Callable[[Any], Optional[str]],
) -> Dict[str, Any]:
    payload = dict(row or {})
    raw_type = str(payload.get("event_type") or "").strip().lower()
    payload["event_type"] = normalize_event_type(raw_type)
    payload["raw_event_type"] = raw_type or payload["event_type"]
    payload["details"] = parse_json_object_fn(
        payload.get("details") or payload.get("details_json")
    )
    payload["created_at"] = bogota_isoformat(
        payload.get("created_at") or payload.get("creado_en")
    )
    payload.pop("details_json", None)
    return payload


def fetch_audit_event_rows(
    conn,
    *,
    limit: int,
    ensure_audit_events_table: Callable[[Any], None],
    ensure_users_table: Callable[[Any], None],
    serialize_entry: Callable[[Dict[str, Any]], Dict[str, Any]],
) -> List[Dict[str, Any]]:
    cur = conn.cursor(dictionary=True)
    try:
        ensure_audit_events_table(cur)
        ensure_users_table(cur)
        cur.execute(
            """
            SELECT
                ae.id,
                ae.event_type,
                ae.entity_type,
                ae.entity_id,
                ae.description,
                ae.details_json,
                ae.actor_user_id,
                ae.actor_username,
                u.name AS actor_name,
                ae.created_at
            FROM auditoria_eventos ae
            LEFT JOIN usuarios u ON u.id = ae.actor_user_id
            ORDER BY ae.created_at DESC, ae.id DESC
            LIMIT %s
            """,
            (int(limit),),
        )
        rows = cur.fetchall() or []
        return [serialize_entry(row) for row in rows]
    finally:
        cur.close()


def fetch_legacy_price_audit_rows(
    conn,
    *,
    limit: int,
    ensure_price_audit_table: Callable[[Any], None],
    ensure_users_table: Callable[[Any], None],
    serialize_entry: Callable[[Dict[str, Any]], Dict[str, Any]],
) -> List[Dict[str, Any]]:
    cur = conn.cursor(dictionary=True)
    try:
        ensure_price_audit_table(cur)
        ensure_users_table(cur)
        cur.execute(
            """
            SELECT
                pa.id,
                pa.producto_id,
                p.nombre AS producto_nombre,
                pa.usuario_id AS actor_user_id,
                u.username AS actor_username,
                u.name AS actor_name,
                pa.precio_anterior,
                pa.precio_nuevo,
                pa.motivo,
                pa.creado_en
            FROM producto_precio_auditoria pa
            LEFT JOIN productos p ON p.id = pa.producto_id
            LEFT JOIN usuarios u ON u.id = pa.usuario_id
            ORDER BY pa.creado_en DESC, pa.id DESC
            LIMIT %s
            """,
            (int(limit),),
        )
        rows = cur.fetchall() or []
        entries: List[Dict[str, Any]] = []
        for row in rows:
            product_name = str(row.get("producto_nombre") or "").strip()
            product_id = row.get("producto_id")
            description = (
                f'Precio actualizado en "{product_name}"'
                if product_name
                else f"Precio actualizado en producto #{product_id}"
            )
            entries.append(
                serialize_entry(
                    {
                        "id": row.get("id"),
                        "event_type": "precio_actualizado",
                        "entity_type": "producto",
                        "entity_id": product_id,
                        "description": description,
                        "details": {
                            "precio_anterior": float(
                                row.get("precio_anterior") or 0.0
                            ),
                            "precio_nuevo": float(row.get("precio_nuevo") or 0.0),
                            "motivo": row.get("motivo"),
                        },
                        "actor_user_id": row.get("actor_user_id"),
                        "actor_username": row.get("actor_username"),
                        "actor_name": row.get("actor_name"),
                        "created_at": row.get("creado_en"),
                    }
                )
            )
        return entries
    finally:
        cur.close()


def fetch_legacy_inventory_audit_rows(
    conn,
    *,
    limit: int,
    ensure_inventory_movements_table: Callable[[Any], None],
    ensure_users_table: Callable[[Any], None],
    serialize_entry: Callable[[Dict[str, Any]], Dict[str, Any]],
) -> List[Dict[str, Any]]:
    cur = conn.cursor(dictionary=True)
    try:
        ensure_inventory_movements_table(cur)
        ensure_users_table(cur)
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
                m.usuario_id AS actor_user_id,
                u.username AS actor_username,
                u.name AS actor_name,
                m.creado_en
            FROM inventario_movimientos m
            LEFT JOIN productos p ON p.id = m.producto_id
            LEFT JOIN usuarios u ON u.id = m.usuario_id
            ORDER BY m.creado_en DESC, m.id DESC
            LIMIT %s
            """,
            (int(limit),),
        )
        rows = cur.fetchall() or []
        entries: List[Dict[str, Any]] = []
        for row in rows:
            product_name = str(row.get("producto_nombre") or "").strip()
            product_id = row.get("producto_id")
            movement_type = str(row.get("tipo") or "ajuste").strip().lower()
            description = (
                f'Inventario {movement_type} en "{product_name}"'
                if product_name
                else f"Inventario {movement_type} en producto #{product_id}"
            )
            entries.append(
                serialize_entry(
                    {
                        "id": row.get("id"),
                        "event_type": "stock_ajustado",
                        "entity_type": "producto",
                        "entity_id": product_id,
                        "description": description,
                        "details": {
                            "tipo": movement_type,
                            "cantidad": int(row.get("cantidad") or 0),
                            "stock_anterior": int(row.get("stock_anterior") or 0),
                            "stock_nuevo": int(row.get("stock_nuevo") or 0),
                            "motivo": row.get("motivo"),
                        },
                        "actor_user_id": row.get("actor_user_id"),
                        "actor_username": row.get("actor_username"),
                        "actor_name": row.get("actor_name"),
                        "created_at": row.get("creado_en"),
                    }
                )
            )
        return entries
    finally:
        cur.close()


def audit_entry_matches_filters(
    entry: Dict[str, Any],
    *,
    action_filter: Optional[set[str]],
    user_filter: str,
    start_date: Optional[datetime],
    end_date: Optional[datetime],
    include_system: bool,
    normalize_event_type: Callable[[Optional[str]], str],
    to_bogota_datetime: Callable[[Any], Optional[datetime]],
) -> bool:
    if not include_system:
        entity_type = str(entry.get("entity_type") or "").strip().lower()
        if entity_type == "sistema":
            return False
    event_type = normalize_event_type(entry.get("event_type"))
    raw_event_type = str(entry.get("raw_event_type") or event_type).strip().lower()
    if (
        event_type in HIDDEN_AUDIT_EVENT_TYPES
        or raw_event_type in HIDDEN_AUDIT_EVENT_TYPES
    ):
        return False
    if action_filter and event_type not in action_filter and raw_event_type not in action_filter:
        return False
    created_at = to_bogota_datetime(entry.get("created_at"))
    if start_date and end_date:
        if not created_at:
            return False
        created_day = created_at.date()
        if created_day < start_date.date() or created_day > end_date.date():
            return False
    if user_filter:
        haystack = " ".join(
            [
                str(entry.get("actor_name") or ""),
                str(entry.get("actor_username") or ""),
                str(entry.get("description") or ""),
            ]
        ).lower()
        if user_filter not in haystack:
            return False
    return True


def audit_entry_sort_key(
    entry: Dict[str, Any],
    *,
    to_bogota_datetime: Callable[[Any], Optional[datetime]],
    min_datetime: datetime,
) -> Tuple[datetime, int]:
    created_at = to_bogota_datetime(entry.get("created_at")) or min_datetime
    try:
        entry_id = int(entry.get("id") or 0)
    except (TypeError, ValueError):
        entry_id = 0
    return created_at, entry_id


def load_audit_trail_payload(
    *,
    date_from_raw: Optional[str] = None,
    date_to_raw: Optional[str] = None,
    action_raw: Optional[str] = None,
    user_raw: Optional[str] = None,
    limit_raw: Optional[str] = None,
    include_system_raw: Optional[str] = None,
    parse_requested_date_range: Callable[..., Tuple[Any, Any, Any, Any]],
    parse_limit: Callable[..., int],
    resolve_action_filter: Callable[[Optional[str]], Optional[set[str]]],
    get_db_conn: Callable[[], Any],
    fetch_audit_events: Callable[..., List[Dict[str, Any]]],
    fetch_legacy_price: Callable[..., List[Dict[str, Any]]],
    fetch_legacy_inventory: Callable[..., List[Dict[str, Any]]],
    matches_filters: Callable[..., bool],
    sort_key: Callable[[Dict[str, Any]], Tuple[datetime, int]],
    normalize_event_type: Callable[[Optional[str]], str],
) -> Dict[str, Any]:
    date_from, date_to, start_date, end_date = parse_requested_date_range(
        date_from_raw,
        date_to_raw,
        required=False,
    )
    limit = parse_limit(limit_raw, default=400)
    fetch_limit = max(limit, 400)
    action_filter = resolve_action_filter(action_raw)
    user_filter = str(user_raw or "").strip().lower()
    include_system = str(include_system_raw or "1").strip() not in {"0", "false", "no"}
    conn = get_db_conn()
    try:
        entries: List[Dict[str, Any]] = []
        entries.extend(fetch_audit_events(conn, limit=fetch_limit))
        entries.extend(fetch_legacy_price(conn, limit=fetch_limit))
        entries.extend(fetch_legacy_inventory(conn, limit=fetch_limit))
    finally:
        conn.close()
    filtered = [
        entry
        for entry in entries
        if matches_filters(
            entry,
            action_filter=action_filter,
            user_filter=user_filter,
            start_date=start_date,
            end_date=end_date,
            include_system=include_system,
        )
    ]
    filtered.sort(key=sort_key, reverse=True)
    sliced = filtered[:limit]
    summary: Dict[str, Any] = {"total": len(sliced)}
    if date_from and date_to:
        summary["periodo"] = {"desde": date_from, "hasta": date_to}
    if action_filter:
        summary["action"] = normalize_event_type(action_raw)
    if user_filter:
        summary["user"] = user_filter
    return {"success": True, "eventos": sliced, "summary": summary}
