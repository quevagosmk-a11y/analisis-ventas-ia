from __future__ import annotations

from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional


def build_offline_sale_detail_payload(offline: Dict[str, Any]) -> Dict[str, Any]:
    venta = dict(offline or {})
    items = venta.pop("items", [])
    venta["fecha"] = venta.get("fecha")
    venta["total"] = float(venta.get("total") or 0.0)
    venta["subtotal"] = float(venta.get("subtotal") or venta["total"] or 0.0)
    venta["iva_total"] = float(venta.get("iva_total") or 0.0)
    venta["anulada"] = bool(venta.get("anulada"))
    venta["anulacion_autorizada"] = bool(venta.get("anulacion_autorizada"))
    return {"venta": venta, "items": items, "offline": True}


def build_sale_detail_payload(
    venta: Dict[str, Any],
    raw_items: List[Dict[str, Any]],
    rec_row: Optional[Dict[str, Any]],
    *,
    normalize_iva: Callable[[Decimal], Decimal],
    normalize_price: Callable[[Decimal], Decimal],
    bogota_isoformat: Callable[[Any], Optional[str]],
    json_loads: Callable[[str], Any],
) -> Dict[str, Any]:
    try:
        venta_iva_percent = normalize_iva(Decimal(str(venta.get("iva_percent"))))
        if venta_iva_percent <= 0:
            venta_iva_percent = None
    except Exception:
        venta_iva_percent = None
    subtotal_total = Decimal("0.00")
    iva_total = Decimal("0.00")
    items: List[Dict[str, Any]] = []
    item_iva_rates = set()
    for raw_item in raw_items:
        item = dict(raw_item or {})
        cantidad = int(item.get("cantidad") or 0)
        try:
            precio_unitario = normalize_price(Decimal(str(item.get("precio") or 0)))
        except Exception:
            precio_unitario = Decimal("0.00")
        try:
            item_iva_percent = normalize_iva(Decimal(str(item.get("iva_percent"))))
        except Exception:
            item_iva_percent = venta_iva_percent or Decimal("0.00")
        line_subtotal = normalize_price(precio_unitario * Decimal(cantidad))
        unit_iva = normalize_price((precio_unitario * item_iva_percent) / Decimal("100"))
        line_iva = normalize_price(unit_iva * Decimal(cantidad))
        subtotal_total += line_subtotal
        iva_total += line_iva
        item["cantidad"] = cantidad
        item["precio"] = float(precio_unitario)
        item["subtotal"] = float(line_subtotal)
        item["iva_percent"] = float(item_iva_percent)
        item["iva_total"] = float(line_iva)
        item["total_linea"] = float(normalize_price(line_subtotal + line_iva))
        items.append(item)
        item_iva_rates.add(item["iva_percent"])
    subtotal_total = normalize_price(subtotal_total)
    iva_total = normalize_price(iva_total)
    venta_payload = dict(venta)
    venta_payload["fecha"] = bogota_isoformat(venta_payload.get("fecha"))
    venta_payload["total"] = float(venta_payload.get("total") or 0.0)
    venta_payload["subtotal"] = float(subtotal_total)
    venta_payload["iva_total"] = float(iva_total)
    venta_payload["anulada"] = bool(venta_payload.get("anulada"))
    venta_payload["anulacion_autorizada"] = bool(
        venta_payload.get("anulacion_autorizada")
    )
    for field in (
        "anulada_en",
        "anulacion_autorizada_en",
    ):
        venta_payload[field] = bogota_isoformat(venta_payload.get(field))
    if venta_iva_percent is not None:
        venta_payload["iva_porcentaje"] = float(venta_iva_percent)
    elif len(item_iva_rates) == 1:
        venta_payload["iva_porcentaje"] = next(iter(item_iva_rates))
    else:
        venta_payload["iva_porcentaje"] = None
    response: Dict[str, Any] = {"venta": venta_payload, "items": items}
    if rec_row:
        response["recomendaciones"] = {
            "combo_suggestions": json_loads(rec_row.get("combos") or "[]"),
            "restock_alerts": json_loads(rec_row.get("restock") or "[]"),
            "estado": rec_row.get("estado"),
        }
    return response


def load_sale_detail_payload(
    conn,
    venta_id: int,
    *,
    build_sale_detail_payload: Callable[
        [Dict[str, Any], List[Dict[str, Any]], Optional[Dict[str, Any]]], Dict[str, Any]
    ],
    mark_online: Callable[[], None],
) -> Optional[Dict[str, Any]]:
    cur = conn.cursor(dictionary=True)
    cur.execute(
        """
        SELECT v.id, v.fecha, v.total, v.metodo_pago, v.iva_percent,
               COALESCE(v.anulada, 0) AS anulada,
               v.anulada_en,
               v.anulada_por,
               v.anulacion_motivo,
               COALESCE(v.anulacion_autorizada, 0) AS anulacion_autorizada,
               v.anulacion_autorizada_en,
               v.anulacion_autorizada_por,
               u.id AS usuario_id, u.username, u.name
        FROM ventas v
        LEFT JOIN usuarios u ON u.id = v.usuario_id
        WHERE v.id = %s
        """,
        (venta_id,),
    )
    venta = cur.fetchone()
    if not venta:
        return None
    cur.execute(
        """
        SELECT vd.producto_id, p.nombre, vd.cantidad, vd.precio, vd.iva_percent
        FROM venta_detalle vd
        JOIN productos p ON p.id = vd.producto_id
        WHERE vd.venta_id = %s
        """,
        (venta_id,),
    )
    raw_items = cur.fetchall() or []
    cur.execute(
        "SELECT combos, restock, estado FROM venta_recomendaciones WHERE venta_id=%s",
        (venta_id,),
    )
    rec_row = cur.fetchone()
    payload = build_sale_detail_payload(venta, raw_items, rec_row)
    mark_online()
    return payload
