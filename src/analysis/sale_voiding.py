from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

SALE_VOID_AUTH_KEY = "borrar"


def role_can_authorize_sale_void(role: Any) -> bool:
    normalized = str(role or "").strip().lower()
    return normalized in {"gerente", "admin"}


def role_can_execute_sale_void(role: Any) -> bool:
    normalized = str(role or "").strip().lower()
    return normalized in {"vendedor", "admin"}


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "si", "sÃ­", "yes"}


def build_sale_capabilities(
    sale: Dict[str, Any],
    *,
    viewer_role: Any,
    viewer_user_id: Any,
) -> Dict[str, bool]:
    normalized_role = str(viewer_role or "").strip().lower()
    sale_owner_id = int(sale.get("usuario_id") or 0)
    current_user_id = int(viewer_user_id or 0)
    is_owner = sale_owner_id > 0 and sale_owner_id == current_user_id
    is_voided = _coerce_bool(sale.get("anulada"))
    is_authorized = _coerce_bool(sale.get("anulacion_autorizada"))
    can_authorize = (
        role_can_authorize_sale_void(normalized_role)
        and not is_voided
        and normalized_role != "vendedor"
    )
    can_void = False
    if not is_voided and role_can_execute_sale_void(normalized_role):
        if normalized_role == "admin":
            can_void = True
        elif normalized_role == "vendedor" and is_authorized:
            can_void = True
    return {
        "is_owner": is_owner,
        "can_authorize_void": can_authorize,
        "can_void": can_void,
        "authorized_for_void": is_authorized,
        "is_voided": is_voided,
    }


def fetch_recent_sales_rows(
    conn,
    *,
    limit: int,
    viewer_role: Any,
    viewer_user_id: Any,
) -> List[Dict[str, Any]]:
    cur = conn.cursor(dictionary=True)
    try:
        params: List[Any] = [max(1, min(int(limit or 20), 100))]
        cur.execute(
            """
            SELECT
                v.id,
                v.fecha,
                v.total,
                v.metodo_pago,
                v.usuario_id,
                COALESCE(v.anulada, 0) AS anulada,
                COALESCE(v.anulacion_autorizada, 0) AS anulacion_autorizada,
                u.username AS vendedor,
                u.name AS vendedor_nombre
            FROM ventas v
            LEFT JOIN usuarios u ON u.id = v.usuario_id
            ORDER BY v.fecha DESC, v.id DESC
            LIMIT %s
            """,
            tuple(params),
        )
        return cur.fetchall() or []
    finally:
        cur.close()


def load_sale_void_context(cur, sale_id: int) -> Optional[Dict[str, Any]]:
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
            u.username,
            u.name
        FROM ventas v
        LEFT JOIN usuarios u ON u.id = v.usuario_id
        WHERE v.id = %s
        """,
        (int(sale_id),),
    )
    return cur.fetchone()


def authorize_sale_void(
    cur,
    *,
    sale_id: int,
    manager_key: str,
    actor_user_id: Optional[int],
    actor_username: Optional[str],
    auth_key: str,
    load_sale_context: Callable[[Any, int], Optional[Dict[str, Any]]],
    record_audit_event: Callable[..., Any],
) -> Dict[str, Any]:
    sale = load_sale_context(cur, sale_id)
    if not sale:
        raise LookupError("Venta no encontrada.")
    if _coerce_bool(sale.get("anulada")):
        raise ValueError("La venta ya fue deshabilitada.")
    normalized_key = str(manager_key or "").strip().lower()
    if normalized_key != str(auth_key or "").strip().lower():
        raise PermissionError("La clave del gerente es incorrecta.")
    cur.execute(
        """
        UPDATE ventas
        SET anulacion_autorizada=1,
            anulacion_autorizada_en=NOW(),
            anulacion_autorizada_por=%s
        WHERE id=%s
        """,
        (actor_user_id, int(sale_id)),
    )
    record_audit_event(
        cur,
        event_type="venta_anulacion_autorizada",
        entity_type="venta",
        entity_id=int(sale_id),
        description=f"Anulacion autorizada para la venta #{int(sale_id)}",
        details={
            "sale_id": int(sale_id),
            "authorized_for_user_id": int(sale.get("usuario_id") or 0),
        },
        actor_user_id=actor_user_id,
        actor_username=actor_username,
    )
    return {
        "sale_id": int(sale_id),
        "authorized_for_user_id": int(sale.get("usuario_id") or 0),
        "authorized": True,
    }


def void_sale(
    cur,
    *,
    sale_id: int,
    actor_role: Any,
    actor_user_id: Optional[int],
    actor_username: Optional[str],
    reason: str,
    load_sale_context: Callable[[Any, int], Optional[Dict[str, Any]]],
    record_inventory_movement: Callable[..., Any],
    record_audit_event: Callable[..., Any],
) -> Dict[str, Any]:
    sale = load_sale_context(cur, sale_id)
    if not sale:
        raise LookupError("Venta no encontrada.")
    if _coerce_bool(sale.get("anulada")):
        raise ValueError("La venta ya fue deshabilitada.")
    normalized_role = str(actor_role or "").strip().lower()
    if normalized_role == "admin":
        pass
    elif normalized_role != "vendedor":
        raise PermissionError("No tienes permiso para deshabilitar esta venta.")
    elif not _coerce_bool(sale.get("anulacion_autorizada")):
        raise PermissionError(
            "La venta debe ser autorizada por un gerente antes de deshabilitarse."
        )
    cur.execute(
        """
        SELECT vd.producto_id, vd.cantidad, p.nombre
        FROM venta_detalle vd
        LEFT JOIN productos p ON p.id = vd.producto_id
        WHERE vd.venta_id = %s
        """,
        (int(sale_id),),
    )
    detail_rows = cur.fetchall() or []
    restored_items: List[Dict[str, Any]] = []
    for item in detail_rows:
        product_id = int(item.get("producto_id") or 0)
        quantity = int(item.get("cantidad") or 0)
        if product_id <= 0 or quantity <= 0:
            continue
        cur.execute(
            "SELECT id, nombre, stock FROM productos WHERE id=%s",
            (product_id,),
        )
        product = cur.fetchone()
        if not product:
            continue
        previous_stock = int(product.get("stock") or 0)
        new_stock = previous_stock + quantity
        cur.execute("UPDATE productos SET stock=%s WHERE id=%s", (new_stock, product_id))
        record_inventory_movement(
            cur,
            producto_id=product_id,
            tipo="entrada",
            cantidad=quantity,
            stock_anterior=previous_stock,
            stock_nuevo=new_stock,
            motivo=f"Anulacion venta #{int(sale_id)}",
            usuario_id=actor_user_id,
        )
        restored_items.append(
            {
                "producto_id": product_id,
                "nombre": product.get("nombre") or item.get("nombre"),
                "cantidad": quantity,
            }
        )
    cur.execute(
        """
        UPDATE ventas
        SET anulada=1,
            anulada_en=NOW(),
            anulada_por=%s,
            anulacion_motivo=%s,
            anulacion_autorizada=0
        WHERE id=%s
        """,
        (
            actor_user_id,
            (reason or "").strip()[:255] or "Venta deshabilitada por correccion.",
            int(sale_id),
        ),
    )
    record_audit_event(
        cur,
        event_type="venta_deshabilitada",
        entity_type="venta",
        entity_id=int(sale_id),
        description=f"Venta #{int(sale_id)} deshabilitada",
        details={
            "sale_id": int(sale_id),
            "restored_items": restored_items,
            "reason": (reason or "").strip()[:255] or None,
        },
        actor_user_id=actor_user_id,
        actor_username=actor_username,
    )
    return {
        "sale_id": int(sale_id),
        "voided": True,
        "restored_items": restored_items,
    }
