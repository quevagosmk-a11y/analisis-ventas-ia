from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional


def build_purchase_recommendations(
    products: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    return [
        {
            "nombre": prod.get("nombre"),
            "stock": prod.get("stock"),
            "min_stock": prod.get("min_stock"),
            "recomendar_comprar": prod.get("recommended_purchase"),
            "alert_level": prod.get("alert_level"),
            "alert_badge_class": prod.get("alert_badge_class"),
            "alert_message": prod.get("alert_message"),
            "target_stock": prod.get("target_stock"),
        }
        for prod in products
        if prod.get("recommended_purchase")
    ]


def build_dashboard_snapshot_payload(
    snapshot: Dict[str, Any],
    *,
    payment_start: Any,
    payment_end: Any,
    payment_period: Optional[Dict[str, Any]],
    get_sales_report: Callable[[Any, Any], List[Dict[str, Any]]],
    build_payment_breakdown_from_sales: Callable[[List[Dict[str, Any]]], List[Dict[str, Any]]],
    product_needs_stock_alert: Callable[[Dict[str, Any]], bool],
    enrich_product_with_alert: Callable[[Dict[str, Any]], Dict[str, Any]],
    build_purchase_recommendations: Callable[[List[Dict[str, Any]]], List[Dict[str, Any]]],
    enrich_dashboard_payload: Callable[..., Dict[str, Any]],
) -> Dict[str, Any]:
    snapshot = dict(snapshot or {})
    if payment_start and payment_end:
        offline_sales = get_sales_report(payment_start, payment_end)
        snapshot["payment_breakdown"] = build_payment_breakdown_from_sales(
            offline_sales
        )
        snapshot["payment_period"] = payment_period
    products_raw = snapshot.pop("productos", [])
    low_raw = [prod for prod in products_raw if product_needs_stock_alert(prod)]
    products_low_stock = [enrich_product_with_alert(prod) for prod in low_raw]
    snapshot["productos_stock_bajo"] = products_low_stock
    snapshot["recomendaciones_compra"] = build_purchase_recommendations(
        products_low_stock
    )
    snapshot["offline"] = True
    return enrich_dashboard_payload(
        snapshot,
        products_source=products_raw,
        movements_source=snapshot.get("inventario_movimientos") or [],
    )


def load_dashboard_payload(
    conn,
    *,
    payment_period: Optional[Dict[str, Any]],
    payment_from: Optional[str],
    payment_to: Optional[str],
    enrich_product_with_alert: Callable[[Dict[str, Any]], Dict[str, Any]],
    build_purchase_recommendations: Callable[[List[Dict[str, Any]]], List[Dict[str, Any]]],
    enrich_dashboard_payload: Callable[..., Dict[str, Any]],
    mark_online: Callable[[], None],
) -> Dict[str, Any]:
    cur = conn.cursor(dictionary=True)
    cur.execute(
        """
        SELECT IFNULL(SUM(total),0) as ventas_hoy
        FROM ventas
        WHERE DATE(fecha)=CURDATE()
          AND COALESCE(anulada, 0)=0
        """
    )
    ventas_hoy = float(cur.fetchone()["ventas_hoy"])
    cur.execute(
        """
        SELECT COUNT(*) as stock_bajo
        FROM productos
        WHERE stock <= min_stock
           OR (stock > min_stock AND stock - min_stock <= GREATEST(1, ROUND(min_stock * 0.2)))
        """
    )
    stock_bajo = cur.fetchone()["stock_bajo"]
    cur.execute("SELECT COUNT(*) as total_productos FROM productos")
    total_productos = cur.fetchone()["total_productos"]
    try:
        cur.execute(
            """
            SELECT COUNT(*) AS total
            FROM productos
            WHERE imagen_blob IS NULL OR OCTET_LENGTH(imagen_blob)=0
            """
        )
        products_without_image = int((cur.fetchone() or {}).get("total") or 0)
    except Exception:
        products_without_image = 0
    cur.execute(
        """
        SELECT p.nombre, SUM(vd.cantidad) AS total_vendido
        FROM venta_detalle vd
        JOIN ventas v ON v.id = vd.venta_id
        JOIN productos p ON p.id = vd.producto_id
        WHERE v.fecha >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)
          AND COALESCE(v.anulada, 0)=0
        GROUP BY p.nombre
        ORDER BY total_vendido DESC
        LIMIT 5
        """
    )
    popular_products = cur.fetchall()
    cur.execute(
        """
        SELECT id, nombre, stock, min_stock
        FROM productos
        WHERE stock <= min_stock
           OR (stock > min_stock AND stock - min_stock <= GREATEST(1, ROUND(min_stock * 0.2)))
        ORDER BY stock ASC
        """
    )
    products_low_stock = [enrich_product_with_alert(row) for row in cur.fetchall()]
    purchase_recommendations = build_purchase_recommendations(products_low_stock)
    critical_stock = sum(
        1
        for prod in products_low_stock
        if str(prod.get("alert_level") or "").lower() == "critico"
    )
    try:
        cur.execute(
            """
            SELECT id, nombre, categoria
            FROM productos
            WHERE imagen_blob IS NULL OR OCTET_LENGTH(imagen_blob)=0
            ORDER BY nombre ASC
            LIMIT 6
            """
        )
        products_without_image_detail = cur.fetchall() or []
    except Exception:
        products_without_image_detail = []
    try:
        cur.execute(
            """
            SELECT
                m.id,
                m.producto_id,
                p.nombre AS producto_nombre,
                m.tipo,
                m.cantidad,
                u.username AS usuario,
                m.creado_en
            FROM inventario_movimientos m
            LEFT JOIN productos p ON p.id = m.producto_id
            LEFT JOIN usuarios u ON u.id = m.usuario_id
            ORDER BY m.creado_en DESC
            LIMIT 6
            """
        )
        recent_movements = cur.fetchall() or []
    except Exception:
        recent_movements = []
    if payment_period:
        cur.execute(
            """
            SELECT metodo_pago, COUNT(*) AS total_ventas, SUM(total) AS monto_total
            FROM ventas
            WHERE DATE(fecha) BETWEEN %s AND %s
              AND COALESCE(anulada, 0)=0
            GROUP BY metodo_pago
            ORDER BY monto_total DESC
            """,
            (payment_from, payment_to),
        )
    else:
        cur.execute(
            """
            SELECT metodo_pago, COUNT(*) AS total_ventas, SUM(total) AS monto_total
            FROM ventas
            WHERE COALESCE(anulada, 0)=0
            GROUP BY metodo_pago
            ORDER BY monto_total DESC
            """
        )
    payment_breakdown = cur.fetchall() or []
    for entry in payment_breakdown:
        entry["total_ventas"] = int(entry.get("total_ventas") or 0)
        entry["monto_total"] = float(entry.get("monto_total") or 0.0)
    mark_online()
    return enrich_dashboard_payload(
        {
            "ventas_hoy": ventas_hoy,
            "stock_bajo": stock_bajo,
            "stock_critico": critical_stock,
            "total_productos": total_productos,
            "productos_sin_imagen": products_without_image,
            "productos_populares": popular_products,
            "productos_stock_bajo": products_low_stock,
            "recomendaciones_compra": purchase_recommendations,
            "productos_sin_imagen_detalle": products_without_image_detail,
            "movimientos_recientes": recent_movements,
            "payment_breakdown": payment_breakdown,
            "payment_period": payment_period,
        },
        products_source=products_without_image_detail,
        movements_source=recent_movements,
    )
