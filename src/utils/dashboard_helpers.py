from __future__ import annotations

import unicodedata
from typing import Any, Dict, List, Optional


def normalize_lookup_text(value: Any) -> str:
    raw = str(value or "").strip().lower()
    normalized = unicodedata.normalize("NFD", raw)
    without_accents = "".join(
        ch for ch in normalized if unicodedata.category(ch) != "Mn"
    )
    return " ".join(without_accents.split())


def enrich_product_with_alert(prod: Dict[str, Any]) -> Dict[str, Any]:
    stock_val = prod.get("stock")
    min_stock_val = prod.get("min_stock")
    try:
        stock = int(stock_val) if stock_val is not None else None
    except (TypeError, ValueError):
        stock = None
    try:
        min_stock = int(min_stock_val) if min_stock_val is not None else None
    except (TypeError, ValueError):
        min_stock = None

    alert_level = "ok"
    badge = "bg-success"
    message = "Stock dentro de rango."
    recommended = 0
    target_stock = None
    if min_stock is None or min_stock < 0:
        alert_level = "sin-configuracion"
        badge = "bg-secondary"
        message = "Define un stock mínimo para activar alertas."
    else:
        target_stock = max(min_stock * 2, min_stock + max(3, min_stock // 2))
        if stock is None:
            alert_level = "sin-datos"
            badge = "bg-secondary"
            message = "No se pudo leer el stock actual."
            recommended = target_stock
        else:
            if stock <= 0:
                alert_level = "critico"
                badge = "bg-danger"
                message = "Sin stock disponible."
            elif stock <= max(1, min_stock // 2):
                alert_level = "critico"
                badge = "bg-danger"
                message = "Por debajo del 50% del mínimo."
            elif stock <= min_stock:
                alert_level = "alto"
                badge = "bg-warning"
                message = "Por debajo del mínimo configurado."
            elif stock - min_stock <= max(1, int(round(min_stock * 0.2))):
                alert_level = "seguimiento"
                badge = "bg-warning"
                message = "Muy cerca del mínimo."
            recommended = max((target_stock or min_stock) - stock, 0)
    enriched = dict(prod)
    enriched.update(
        {
            "stock": stock,
            "min_stock": min_stock,
            "alert_level": alert_level,
            "alert_badge": badge,
            "alert_badge_class": badge,
            "alert_message": message,
            "recommended_purchase": recommended,
            "target_stock": target_stock,
        }
    )
    return enriched


def product_needs_stock_alert(prod: Dict[str, Any]) -> bool:
    stock_val = prod.get("stock")
    min_stock_val = prod.get("min_stock")
    try:
        stock = int(stock_val) if stock_val is not None else None
    except (TypeError, ValueError):
        stock = None
    try:
        min_stock = int(min_stock_val) if min_stock_val is not None else None
    except (TypeError, ValueError):
        min_stock = None
    if stock is None or min_stock is None or min_stock < 0:
        return False
    if stock <= min_stock:
        return True
    return (stock - min_stock) <= max(1, int(round(min_stock * 0.2)))


def build_products_without_image_rows(
    products: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    missing = [
        {
            "id": item.get("id"),
            "nombre": item.get("nombre"),
            "categoria": item.get("categoria"),
        }
        for item in products
        if not str(item.get("imagen_url") or item.get("image_url") or "").strip()
    ]
    missing.sort(key=lambda entry: normalize_lookup_text(entry.get("nombre")))
    return missing


def build_recent_movements_rows(
    rows: List[Dict[str, Any]], *, limit: int = 6
) -> List[Dict[str, Any]]:
    ordered = sorted(
        rows,
        key=lambda item: str(item.get("creado_en") or item.get("created_at") or ""),
        reverse=True,
    )
    payload: List[Dict[str, Any]] = []
    for row in ordered[:limit]:
        payload.append(
            {
                "id": row.get("id"),
                "producto_id": row.get("producto_id"),
                "producto_nombre": row.get("producto_nombre") or row.get("nombre"),
                "tipo": row.get("tipo"),
                "cantidad": int(row.get("cantidad") or 0),
                "usuario": row.get("usuario"),
                "creado_en": row.get("creado_en") or row.get("created_at"),
            }
        )
    return payload


def enrich_dashboard_payload(
    payload: Dict[str, Any],
    *,
    products_source: Optional[List[Dict[str, Any]]] = None,
    movements_source: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    products = products_source or []
    low_stock = payload.get("productos_stock_bajo") or []
    critical_stock = [
        item
        for item in low_stock
        if str(item.get("alert_level") or "").lower() == "critico"
    ]
    products_without_image = build_products_without_image_rows(products)
    payload["stock_critico"] = int(payload.get("stock_critico") or len(critical_stock))
    if "productos_sin_imagen" not in payload:
        payload["productos_sin_imagen"] = len(products_without_image)
    if "productos_sin_imagen_detalle" not in payload:
        payload["productos_sin_imagen_detalle"] = products_without_image[:6]
    if "movimientos_recientes" not in payload:
        payload["movimientos_recientes"] = build_recent_movements_rows(
            movements_source or []
        )
    return payload
