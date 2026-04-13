from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple


def parse_requested_date_range(
    date_from_raw: Optional[str],
    date_to_raw: Optional[str],
    *,
    required: bool = False,
) -> Tuple[Optional[str], Optional[str], Optional[datetime], Optional[datetime]]:
    date_from = (date_from_raw or "").strip()
    date_to = (date_to_raw or "").strip()
    if not date_from and not date_to:
        if required:
            raise ValueError("Debe indicar from y to")
        return None, None, None, None
    if bool(date_from) ^ bool(date_to):
        raise ValueError("Debe indicar from y to")
    try:
        start_date = datetime.strptime(date_from, "%Y-%m-%d")
        end_date = datetime.strptime(date_to, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError("Formato de fecha inválido. Usa YYYY-MM-DD") from exc
    if start_date > end_date:
        raise ValueError("El rango de fechas es inválido")
    return date_from, date_to, start_date, end_date


def summarize_sales_report_rows(ventas: List[Dict[str, Any]]) -> Dict[str, Any]:
    active_sales = [venta for venta in ventas if not bool(venta.get("anulada"))]
    return {
        "ventas_registradas": len(active_sales),
        "total_productos": sum(int(row.get("items") or 0) for row in active_sales),
        "monto_total": round(
            sum(float(row.get("total") or 0.0) for row in active_sales), 2
        ),
    }


def build_payment_breakdown_from_sales(
    ventas: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    grouped: Dict[str, Dict[str, Any]] = {}
    for venta in ventas:
        if bool(venta.get("anulada")):
            continue
        method = (venta.get("metodo_pago") or "Desconocido").strip() or "Desconocido"
        bucket = grouped.setdefault(
            method,
            {"metodo_pago": method, "total_ventas": 0, "monto_total": 0.0},
        )
        bucket["total_ventas"] += 1
        bucket["monto_total"] += float(venta.get("total") or 0.0)
    rows = list(grouped.values())
    rows.sort(key=lambda item: item["monto_total"], reverse=True)
    for row in rows:
        row["total_ventas"] = int(row.get("total_ventas") or 0)
        row["monto_total"] = round(float(row.get("monto_total") or 0.0), 2)
    return rows


def fetch_sales_report_rows(
    conn,
    date_from: str,
    date_to: str,
    *,
    viewer_role: Optional[str] = None,
    viewer_user_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    cur = conn.cursor(dictionary=True)
    try:
        params: List[Any] = [date_from, date_to]
        cur.execute(
            """
            SELECT v.id, v.fecha, v.total, v.metodo_pago,
                   COALESCE(v.anulada, 0) AS anulada,
                   COALESCE(v.anulacion_autorizada, 0) AS anulacion_autorizada,
                   u.username AS vendedor,
                   SUM(vd.cantidad) AS items
            FROM ventas v
            JOIN usuarios u ON u.id = v.usuario_id
            JOIN venta_detalle vd ON vd.venta_id = v.id
            WHERE DATE(v.fecha) BETWEEN %s AND %s
            GROUP BY v.id, v.fecha, v.total, v.metodo_pago, COALESCE(v.anulada, 0), COALESCE(v.anulacion_autorizada, 0), u.username
            ORDER BY v.fecha DESC
            """,
            tuple(params),
        )
        return cur.fetchall() or []
    finally:
        cur.close()


def _empty_ai_report_sections() -> Dict[str, Any]:
    return {
        "metadata": None,
        "productos_alta_rotacion": [],
        "recomendaciones_reposicion": [],
        "tendencias_predichas": [],
        "predicciones_demanda": {},
    }


def load_sales_report_payload(
    date_from_raw: str,
    date_to_raw: str,
    *,
    get_db_conn: Callable[[], Any],
    offline_cache: Any,
    build_ai_report_payload: Callable[..., Dict[str, Any]],
    viewer_role: Optional[str] = None,
    viewer_user_id: Optional[int] = None,
    viewer_username: Optional[str] = None,
) -> Dict[str, Any]:
    date_from, date_to, start_date, end_date = parse_requested_date_range(
        date_from_raw,
        date_to_raw,
        required=True,
    )
    assert date_from and date_to and start_date and end_date
    period_payload = {"desde": date_from, "hasta": date_to}
    try:
        conn = get_db_conn()
    except Exception as exc:
        print(f"[reportes] sin conexion para ventas: {exc}")
        offline_cache.mark_offline(str(exc))
        ventas_offline = offline_cache.get_sales_report(start_date, end_date)
        if ventas_offline:
            return {
                "success": True,
                "ventas": ventas_offline,
                "resumen": summarize_sales_report_rows(ventas_offline),
                "periodo": period_payload,
                "offline": True,
                **_empty_ai_report_sections(),
            }
        raise RuntimeError("No hay datos locales para el periodo solicitado.") from exc
    try:
        ventas = fetch_sales_report_rows(
            conn,
            date_from,
            date_to,
            viewer_role=viewer_role,
            viewer_user_id=viewer_user_id,
        )
        offline_cache.mark_online()
        ai_report = None
        try:
            ai_report = build_ai_report_payload(date_from=date_from, date_to=date_to)
        except Exception as exc:
            print(f"[reportes] no se pudo generar reporte IA: {exc}")
        payload: Dict[str, Any] = {
            "success": True,
            "ventas": ventas,
            "resumen": summarize_sales_report_rows(ventas),
            "periodo": period_payload,
        }
        if ai_report:
            payload.update(
                {
                    "metadata": ai_report.get("metadata"),
                    "productos_alta_rotacion": ai_report.get(
                        "productos_alta_rotacion", []
                    ),
                    "recomendaciones_reposicion": ai_report.get(
                        "recomendaciones_reposicion", []
                    ),
                    "tendencias_predichas": ai_report.get("tendencias_predichas", []),
                    "predicciones_demanda": ai_report.get("predicciones_demanda", {}),
                }
            )
        else:
            payload.update(_empty_ai_report_sections())
        return payload
    except Exception as exc:
        print(f"[reportes] error consultando ventas: {exc}")
        offline_cache.mark_offline(str(exc))
        ventas_offline = offline_cache.get_sales_report(start_date, end_date)
        if ventas_offline:
            return {
                "success": True,
                "ventas": ventas_offline,
                "resumen": summarize_sales_report_rows(ventas_offline),
                "periodo": period_payload,
                "offline": True,
                **_empty_ai_report_sections(),
            }
        raise RuntimeError("No se pudo generar el reporte de ventas.") from exc
    finally:
        conn.close()


def summarize_product_statistics_rows(
    productos: List[Dict[str, Any]]
) -> Dict[str, Any]:
    return {
        "total_productos": len(productos),
        "total_unidades": int(
            round(sum(float(item.get("cantidad") or 0.0) for item in productos))
        ),
        "monto_total": round(
            sum(float(item.get("ingresos") or 0.0) for item in productos), 2
        ),
    }


def fetch_product_statistics_rows(
    conn,
    *,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    days: int = 7,
) -> List[Dict[str, Any]]:
    cur = conn.cursor(dictionary=True)
    try:
        if date_from and date_to:
            cur.execute(
                """
                SELECT p.nombre, SUM(vd.cantidad) AS cantidad, SUM(vd.cantidad * vd.precio) AS ingresos
                FROM venta_detalle vd
                JOIN ventas v ON v.id = vd.venta_id
                JOIN productos p ON p.id = vd.producto_id
                WHERE DATE(v.fecha) BETWEEN %s AND %s
                  AND COALESCE(v.anulada, 0)=0
                GROUP BY p.nombre
                ORDER BY cantidad DESC
                LIMIT 10
                """,
                (date_from, date_to),
            )
        else:
            cur.execute(
                """
                SELECT p.nombre, SUM(vd.cantidad) AS cantidad, SUM(vd.cantidad * vd.precio) AS ingresos
                FROM venta_detalle vd
                JOIN ventas v ON v.id = vd.venta_id
                JOIN productos p ON p.id = vd.producto_id
                WHERE v.fecha >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
                  AND COALESCE(v.anulada, 0)=0
                GROUP BY p.nombre
                ORDER BY cantidad DESC
                LIMIT 10
                """,
                (days,),
            )
        return cur.fetchall() or []
    finally:
        cur.close()


def load_product_stats_payload(
    *,
    date_from_raw: Optional[str] = None,
    date_to_raw: Optional[str] = None,
    periodo: str = "mes",
    get_db_conn: Callable[[], Any],
    offline_cache: Any,
) -> Dict[str, Any]:
    date_from, date_to, _, _ = parse_requested_date_range(
        date_from_raw,
        date_to_raw,
        required=False,
    )
    periodo_normalized = (
        "mes" if (periodo or "").strip().lower() == "mes" else "semana"
    )
    days = 30 if periodo_normalized == "mes" else 7
    period_payload = (
        {"desde": date_from, "hasta": date_to} if date_from and date_to else None
    )
    period_label = "rango_personalizado" if period_payload else periodo_normalized
    try:
        conn = get_db_conn()
    except Exception as exc:
        print(f"[estadisticas] sin conexion: {exc}")
        offline_cache.mark_offline(str(exc))
        productos = (
            offline_cache.get_top_products(date_from=date_from, date_to=date_to)
            if period_payload
            else offline_cache.get_top_products(days)
        )
        if productos:
            payload: Dict[str, Any] = {
                "success": True,
                "periodo": period_label,
                "productos": productos,
                "resumen": summarize_product_statistics_rows(productos),
                "offline": True,
            }
            if period_payload:
                payload["period"] = period_payload
            return payload
        raise RuntimeError("No hay datos locales para estadisticas.") from exc
    try:
        productos = fetch_product_statistics_rows(
            conn,
            date_from=date_from,
            date_to=date_to,
            days=days,
        )
        offline_cache.mark_online()
        payload = {
            "success": True,
            "periodo": period_label,
            "productos": productos,
            "resumen": summarize_product_statistics_rows(productos),
        }
        if period_payload:
            payload["period"] = period_payload
        return payload
    except Exception as exc:
        print(f"[estadisticas] error consultando: {exc}")
        offline_cache.mark_offline(str(exc))
        productos = (
            offline_cache.get_top_products(date_from=date_from, date_to=date_to)
            if period_payload
            else offline_cache.get_top_products(days)
        )
        if productos:
            payload = {
                "success": True,
                "periodo": period_label,
                "productos": productos,
                "resumen": summarize_product_statistics_rows(productos),
                "offline": True,
            }
            if period_payload:
                payload["period"] = period_payload
            return payload
        raise RuntimeError("No se pudieron generar las estadisticas.") from exc
    finally:
        conn.close()
