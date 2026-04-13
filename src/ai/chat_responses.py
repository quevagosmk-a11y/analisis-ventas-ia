from __future__ import annotations

import math
from collections import Counter
from itertools import combinations
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from analysis.recommender import Recommender

from .chat_queries import (
    format_currency_basic,
    handle_custom_chat_request,
    normalize_query_text,
)


def compute_chat_insights(
    sales_df: pd.DataFrame,
    inventory_rows: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    if sales_df is None or sales_df.empty:
        return {
            "base": {
                "top_product": {},
                "top_3_products": [],
                "daily_revenue": [],
                "offer_suggestions": [],
            },
            "latest_date": None,
            "weekly": {"total_revenue": 0.0, "change_pct": None, "top_products": []},
            "monthly": {"total_revenue": 0.0, "change_pct": None, "top_products": []},
            "trending_products": [],
            "restock_candidates": [],
            "best_day": None,
            "totals": {"revenue": 0.0, "units": 0},
            "inventory_snapshot": False,
            "combo_suggestions": [],
            "hourly_patterns": {"top_hours": [], "daypart_summary": []},
            "payment_breakdown": [],
            "predictive_alerts": [],
            "expected_high_demand": [],
            "product_profiles": [],
            "product_keyword_map": {},
        }

    df = sales_df.copy()
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    else:
        df["timestamp"] = pd.to_datetime(df["date"], errors="coerce")
    df["timestamp"] = df["timestamp"].fillna(pd.Timestamp.utcnow())
    df["date"] = df["timestamp"].dt.date
    df["qty"] = pd.to_numeric(df.get("qty"), errors="coerce").fillna(0).astype(int)
    df["total"] = pd.to_numeric(df.get("total"), errors="coerce").fillna(0.0)
    if "order_id" in df.columns:
        df["order_id"] = df["order_id"].astype(str)
    if "payment_method" in df.columns:
        df["payment_method"] = df["payment_method"].fillna("Desconocido")

    recommender = Recommender(df)
    base = recommender.analyze_sales()

    latest_ts = df["timestamp"].max()
    if pd.isna(latest_ts):
        latest_ts = pd.Timestamp.utcnow()
    latest_date = str(latest_ts.date())

    def period_stats(days: int) -> Tuple[pd.DataFrame, pd.DataFrame]:
        end = latest_ts
        start = end - pd.Timedelta(days=days - 1)
        prev_start = start - pd.Timedelta(days=days)
        current = df[df["timestamp"] >= start]
        previous = df[(df["timestamp"] >= prev_start) & (df["timestamp"] < start)]
        return current, previous

    weekly_df, prev_week_df = period_stats(7)
    weekly_total = float(weekly_df["total"].sum())
    prev_week_total = float(prev_week_df["total"].sum())
    weekly_change = (
        ((weekly_total - prev_week_total) / prev_week_total * 100)
        if prev_week_total > 0
        else None
    )
    weekly_top_products = [
        {"product": product, "qty": int(qty)}
        for product, qty in weekly_df.groupby("product")["qty"]
        .sum()
        .sort_values(ascending=False)
        .head(5)
        .items()
    ]

    monthly_df, prev_month_df = period_stats(30)
    monthly_total = float(monthly_df["total"].sum())
    prev_month_total = float(prev_month_df["total"].sum())
    monthly_change = (
        ((monthly_total - prev_month_total) / prev_month_total * 100)
        if prev_month_total > 0
        else None
    )
    monthly_top_products = [
        {"product": product, "qty": int(qty)}
        for product, qty in monthly_df.groupby("product")["qty"]
        .sum()
        .sort_values(ascending=False)
        .head(5)
        .items()
    ]

    prev_qty_series = (
        prev_month_df.groupby("product")["qty"].sum()
        if not prev_month_df.empty
        else pd.Series(dtype=float)
    )
    trending_products = []
    monthly_qty_series = (
        monthly_df.groupby("product")["qty"].sum()
        if not monthly_df.empty
        else pd.Series(dtype=float)
    )
    for product, qty in monthly_qty_series.sort_values(ascending=False).head(5).items():
        previous_qty = float(prev_qty_series.get(product, 0.0))
        change_pct = None
        if previous_qty > 0:
            change_pct = ((float(qty) - previous_qty) / previous_qty) * 100
        trending_products.append(
            {
                "product": product,
                "current_qty": int(qty),
                "change_pct": None if change_pct is None else float(change_pct),
            }
        )

    daily = df.groupby(df["timestamp"].dt.date)["total"].sum().sort_index()
    best_day = None
    if not daily.empty:
        best_date = daily.idxmax()
        best_day = {"date": str(best_date), "revenue": float(daily.loc[best_date])}

    totals = {
        "revenue": float(df["total"].sum()),
        "units": int(df["qty"].sum()),
    }

    inventory_rows = inventory_rows or []
    inventory_snapshot = bool(inventory_rows)
    inventory_map = {
        (row.get("nombre") or "").strip().lower(): row
        for row in inventory_rows
        if row.get("nombre")
    }

    lookback_days = 14
    demand_window = df[
        df["timestamp"] >= latest_ts - pd.Timedelta(days=lookback_days - 1)
    ]
    demand_series = (
        demand_window.groupby("product")["qty"].sum() / lookback_days
        if not demand_window.empty
        else pd.Series(dtype=float)
    )
    demand_map = {
        product.lower(): float(val) for product, val in demand_series.items() if val > 0
    }

    restock_candidates: List[Dict[str, Any]] = []
    weekly_qty_series = (
        weekly_df.groupby("product")["qty"].sum()
        if not weekly_df.empty
        else pd.Series(dtype=float)
    )
    for product, qty in weekly_qty_series.sort_values(ascending=False).head(8).items():
        key = product.strip().lower()
        info = inventory_map.get(key)
        stock_val = info.get("stock") if info else None
        min_stock_val = info.get("min_stock") if info else None
        try:
            stock_int = int(stock_val) if stock_val is not None else None
        except (TypeError, ValueError):
            stock_int = None
        try:
            min_stock_int = int(min_stock_val) if min_stock_val is not None else None
        except (TypeError, ValueError):
            min_stock_int = None
        include = False
        if stock_int is not None and min_stock_int is not None:
            if stock_int <= min_stock_int or stock_int - min_stock_int < qty:
                include = True
        elif stock_int is None:
            include = True
        if include:
            cover_days = None
            daily_qty = demand_map.get(key)
            if daily_qty and stock_int is not None and daily_qty > 0:
                cover_days = stock_int / daily_qty
            restock_candidates.append(
                {
                    "product": product,
                    "weekly_qty": int(qty),
                    "stock": stock_int,
                    "min_stock": min_stock_int,
                    "cover_days": None if cover_days is None else float(cover_days),
                }
            )
    restock_candidates = restock_candidates[:5]

    combos: List[Dict[str, Any]] = []
    if "order_id" in df.columns:
        combo_scope = df.dropna(subset=["order_id"])
        combo_scope = combo_scope[
            combo_scope["timestamp"] >= latest_ts - pd.Timedelta(days=30)
        ]
        total_orders = combo_scope["order_id"].nunique()
        combo_counter = Counter()
        revenue_counter = Counter()
        for _, order in combo_scope.groupby("order_id"):
            products = sorted({str(p) for p in order["product"].dropna()})
            if len(products) < 2 or len(products) > 8:
                continue
            for product_a, product_b in combinations(products, 2):
                combo_counter[(product_a, product_b)] += 1
                revenue_counter[(product_a, product_b)] += float(
                    order.loc[
                        order["product"].isin([product_a, product_b]), "total"
                    ].sum()
                )
        for (product_a, product_b), count in combo_counter.most_common(5):
            support_pct = (count / total_orders * 100) if total_orders else None
            avg_ticket = revenue_counter[(product_a, product_b)] / count if count else 0.0
            combos.append(
                {
                    "products": [product_a, product_b],
                    "count": int(count),
                    "support_pct": None if support_pct is None else float(support_pct),
                    "avg_ticket": float(avg_ticket),
                }
            )

    hourly_patterns = {"top_hours": [], "daypart_summary": []}
    hourly_scope = df[df["timestamp"] >= latest_ts - pd.Timedelta(days=30)]
    if not hourly_scope.empty:
        hourly_scope = hourly_scope.dropna(subset=["timestamp"]).assign(
            hour=hourly_scope["timestamp"].dt.hour
        )
        hourly_qty = hourly_scope.groupby("hour")["qty"].sum()
        hourly_revenue = hourly_scope.groupby("hour")["total"].sum()
        hourly_patterns["top_hours"] = [
            {
                "hour": int(hour),
                "qty": int(hourly_qty.loc[hour]),
                "revenue": float(hourly_revenue.get(hour, 0.0)),
            }
            for hour in hourly_qty.sort_values(ascending=False).head(5).index
        ]
        dayparts = {
            "madrugada": range(0, 6),
            "mañana": range(6, 12),
            "tarde": range(12, 18),
            "noche": range(18, 24),
        }
        summary = []
        for label, hours in dayparts.items():
            mask = hourly_scope["hour"].isin(hours)
            if not mask.any():
                continue
            summary.append(
                {
                    "label": label,
                    "qty": int(hourly_scope.loc[mask, "qty"].sum()),
                    "revenue": float(hourly_scope.loc[mask, "total"].sum()),
                }
            )
        hourly_patterns["daypart_summary"] = summary

    payment_breakdown = []
    if "payment_method" in df.columns:
        payment_totals = (
            df.groupby("payment_method")["total"].sum().sort_values(ascending=False)
        )
        grand_total = payment_totals.sum()
        for method, value in payment_totals.items():
            share_pct = (value / grand_total * 100) if grand_total else None
            payment_breakdown.append(
                {
                    "method": method or "Desconocido",
                    "revenue": float(value),
                    "share_pct": None if share_pct is None else float(share_pct),
                }
            )

    product_profiles = []
    product_keyword_map: Dict[str, List[str]] = {}
    product_totals = (
        df.groupby("product")
        .agg(qty=("qty", "sum"), revenue=("total", "sum"))
        .sort_values("qty", ascending=False)
    )
    for product in product_totals.head(20).index:
        profile = {
            "name": product,
            "total_qty": int(product_totals.loc[product, "qty"]),
            "total_revenue": float(product_totals.loc[product, "revenue"]),
            "weekly_qty": (
                int(weekly_df.groupby("product")["qty"].sum().get(product, 0))
                if not weekly_df.empty
                else 0
            ),
            "monthly_qty": (
                int(monthly_df.groupby("product")["qty"].sum().get(product, 0))
                if not monthly_df.empty
                else 0
            ),
            "share_pct": (
                float((product_totals.loc[product, "qty"] / totals["units"]) * 100)
                if totals["units"]
                else 0.0
            ),
            "peak_hour": None,
        }
        product_rows = df[df["product"] == product]
        if not product_rows.empty:
            hour_series = (
                product_rows.groupby(product_rows["timestamp"].dt.hour)["qty"]
                .sum()
                .sort_values(ascending=False)
            )
            if not hour_series.empty:
                profile["peak_hour"] = {
                    "hour": int(hour_series.index[0]),
                    "qty": int(hour_series.iloc[0]),
                }
        product_profiles.append(profile)
        for token in [
            token for token in str(product).lower().split() if len(token) >= 3
        ]:
            product_keyword_map.setdefault(token, set()).add(product)
    product_keyword_map = {
        token: sorted(list(names)) for token, names in product_keyword_map.items()
    }

    predictive_alerts = []
    expected_high_demand = []
    for row in inventory_rows:
        name = (row.get("nombre") or "").strip()
        if not name:
            continue
        key = name.lower()
        stock_val = row.get("stock")
        min_stock_val = row.get("min_stock")
        try:
            stock_int = int(stock_val) if stock_val is not None else None
        except (TypeError, ValueError):
            stock_int = None
        try:
            min_stock_int = int(min_stock_val) if min_stock_val is not None else None
        except (TypeError, ValueError):
            min_stock_int = None
        daily_qty = demand_map.get(key)
        if daily_qty and stock_int is not None and daily_qty > 0:
            cover_days = stock_int / daily_qty
            if cover_days <= 21 or (
                min_stock_int is not None and stock_int <= min_stock_int
            ):
                predictive_alerts.append(
                    {
                        "product": name,
                        "daily_demand": float(daily_qty),
                        "stock": stock_int,
                        "min_stock": min_stock_int,
                        "cover_days": float(cover_days),
                        "projected_runout_date": str(
                            (latest_ts + pd.Timedelta(days=cover_days)).date()
                        ),
                        "severity": (
                            "alta"
                            if cover_days <= 7
                            or (
                                min_stock_int is not None and stock_int <= min_stock_int
                            )
                            else "media"
                        ),
                    }
                )
    for item in trending_products:
        change = item.get("change_pct")
        if change is not None and change >= 20.0:
            expected_high_demand.append(
                {
                    "product": item["product"],
                    "change_pct": float(change),
                    "reason": f"Crecio {change:.1f}% vs periodo anterior",
                }
            )

    return {
        "base": base,
        "latest_date": latest_date,
        "weekly": {
            "total_revenue": weekly_total,
            "change_pct": None if weekly_change is None else float(weekly_change),
            "top_products": weekly_top_products,
        },
        "monthly": {
            "total_revenue": monthly_total,
            "change_pct": None if monthly_change is None else float(monthly_change),
            "top_products": monthly_top_products,
        },
        "trending_products": trending_products,
        "restock_candidates": restock_candidates,
        "best_day": best_day,
        "totals": totals,
        "inventory_snapshot": inventory_snapshot,
        "combo_suggestions": combos,
        "hourly_patterns": hourly_patterns,
        "payment_breakdown": payment_breakdown,
        "predictive_alerts": predictive_alerts,
        "expected_high_demand": expected_high_demand,
        "product_profiles": product_profiles,
        "product_keyword_map": {
            token: sorted(list(names)) for token, names in product_keyword_map.items()
        },
    }


def build_chat_help_response(insights: Optional[Dict[str, Any]] = None) -> str:
    latest_date = (insights or {}).get("latest_date")
    lines = [
        "Puedo ayudarte con ventas, inventario, reposicion, top productos y metodos de pago."
    ]
    if latest_date:
        lines.append(f"Datos disponibles hasta {latest_date}.")
    lines.append("Prueba con preguntas como:")
    lines.append("- Que producto debo reabastecer primero?")
    lines.append("- Cuales fueron los top 3 productos de la semana?")
    lines.append("- Cual fue el metodo de pago principal del mes?")
    return "\n".join(lines)


def answer_chat_smalltalk(
    question_norm: str, insights: Optional[Dict[str, Any]] = None
) -> Optional[str]:
    if not question_norm:
        return None
    tokens = question_norm.split()
    greeting_phrases = {
        "hola",
        "hola hola",
        "buenas",
        "buen dia",
        "buenos dias",
        "buenas tardes",
        "buenas noches",
        "hey",
        "hello",
        "holi",
        "saludos",
    }
    gratitude_phrases = {
        "gracias",
        "muchas gracias",
        "ok gracias",
        "vale gracias",
    }
    help_phrases = (
        "ayuda",
        "que puedes hacer",
        "que me puedes decir",
        "que consultas puedo hacer",
        "como funcionas",
        "que puedes responder",
        "en que me puedes ayudar",
        "que sabes hacer",
        "quien eres",
        "como estas",
        "como vas",
    )
    if question_norm in greeting_phrases or (
        tokens and tokens[0] in {"hola", "buenas", "hey", "hello", "holi", "saludos"}
    ):
        return "Hola.\n" + build_chat_help_response(insights)
    if question_norm in gratitude_phrases:
        return (
            "Con gusto. Si quieres, reviso ventas, inventario, reposicion o metodos de pago."
        )
    if any(phrase in question_norm for phrase in help_phrases):
        return build_chat_help_response(insights)
    return None


def is_operational_question(question_norm: str) -> bool:
    if not question_norm:
        return False
    keywords = (
        "venta",
        "ventas",
        "vend",
        "ingreso",
        "factur",
        "resumen",
        "producto",
        "productos",
        "top",
        "popular",
        "stock",
        "inventario",
        "reponer",
        "reabaste",
        "reposicion",
        "demanda",
        "pronost",
        "alerta",
        "tendenc",
        "pago",
        "pagos",
        "metodo",
        "metodos",
        "efectivo",
        "nequi",
        "daviplata",
        "transferencia",
        "combo",
        "oferta",
        "promoc",
        "ticket",
        "categoria",
        "precio",
        "precios",
        "semana",
        "mes",
        "hoy",
        "ayer",
    )
    return any(keyword in question_norm for keyword in keywords)


def compose_chat_answer(question: str, insights: Dict[str, Any]) -> str:
    question_lower = question.lower()
    response_lines: List[str] = []

    def format_currency(value: Any) -> str:
        value = 0.0 if value is None else float(value)
        return format_currency_basic(value)

    def format_change(value: Optional[float]) -> Optional[str]:
        if value is None:
            return None
        sign = "+" if value >= 0 else ""
        return f"{sign}{value:.1f}%"

    base = insights.get("base") or {}
    weekly = insights.get("weekly") or {}
    monthly = insights.get("monthly") or {}
    best_day = insights.get("best_day")
    totals = insights.get("totals") or {}
    combos = insights.get("combo_suggestions") or []
    restock_candidates = insights.get("restock_candidates") or []
    trending = insights.get("trending_products") or []
    payment = insights.get("payment_breakdown") or []
    predictive_alerts = insights.get("predictive_alerts") or []
    expected_high_demand = insights.get("expected_high_demand") or []
    latest_date = insights.get("latest_date")
    top_product = base.get("top_product") if isinstance(base, dict) else None

    if latest_date:
        response_lines.append(f"Datos considerados hasta {latest_date}.")

    restock_requested = any(
        token in question_lower
        for token in ("reabaste", "restock", "reponer", "stock", "agot", "inventario")
    )
    if restock_requested:
        if restock_candidates:
            response_lines.append(
                "Prioriza reponer estos productos según demanda y stock actual:"
            )
            for item in restock_candidates[:4]:
                stock_info = ""
                if item.get("stock") is not None:
                    stock_info = f" (stock {item['stock']}"
                    if item.get("min_stock") is not None:
                        stock_info += f", mínimo {item['min_stock']}"
                    stock_info += ")"
                cover_info = ""
                if item.get("cover_days") is not None:
                    cover_info = f", stock para ~{math.ceil(item['cover_days'])} días"
                response_lines.append(
                    f"- {item['product']}: {item['weekly_qty']} uds en 7 días"
                    f"{stock_info}{cover_info}."
                )
        else:
            response_lines.append(
                "No detecto productos urgentes para reabastecer con la data disponible."
            )

    trends_requested = any(
        token in question_lower
        for token in ("tendenc", "trend", "mes", "seman", "comportamiento", "evoluc")
    )
    if trends_requested and trending:
        response_lines.append("Tendencias de los últimos 30 días:")
        for item in trending[:4]:
            change_str = ""
            if item.get("change_pct") is not None:
                change = item["change_pct"]
                change_str = f" ({change:+.1f}% vs periodo anterior)"
            response_lines.append(
                f"- {item['product']}: {item['current_qty']} uds{change_str}."
            )

    combos_requested = any(
        token in question_lower
        for token in ("combo", "oferta", "promoc", "descuento", "bundle", "paquete")
    )
    if combos_requested and combos:
        response_lines.append("Combos sugeridos por compras conjuntas:")
        for combo in combos[:3]:
            pair = " + ".join(combo.get("products") or [])
            detail = f"{combo.get('count', 0)} ventas"
            if combo.get("support_pct") is not None:
                detail += f", {combo['support_pct']:.1f}% de órdenes"
            if combo.get("avg_ticket"):
                detail += f", ticket medio {format_currency(combo['avg_ticket'])}"
            response_lines.append(f"- {pair}: {detail}.")

    payment_requested = any(
        token in question_lower
        for token in (
            "método de pago",
            "metodo de pago",
            "tarjeta",
            "efectivo",
            "nequi",
            "daviplata",
        )
    )
    if payment_requested and payment:
        principal = payment[0]
        share = principal.get("share_pct")
        line = (
            f"Método principal: {principal['method']} con "
            f"{format_currency(principal['revenue'])}"
        )
        if share is not None:
            line += f" ({share:.1f}% de ingresos)"
        response_lines.append(line)

    prediction_requested = any(
        token in question_lower for token in ("anticipa", "alerta", "proyección")
    )
    if prediction_requested and predictive_alerts:
        response_lines.append("Alertas predictivas de stock:")
        for alert in sorted(
            predictive_alerts, key=lambda item: item.get("cover_days", float("inf"))
        )[:3]:
            cover = alert.get("cover_days")
            cover_txt = f" ~{math.ceil(cover)} días" if cover is not None else ""
            response_lines.append(
                f"- {alert['product']}: {alert['daily_demand']:.1f} uds/día, stock "
                f"{alert.get('stock')} (agotaría {alert['projected_runout_date']}"
                f"{cover_txt})."
            )

    if expected_high_demand and not trends_requested:
        names = ", ".join(item["product"] for item in expected_high_demand[:2])
        response_lines.append(f"Prepárate para mayor demanda en: {names}.")

    top_requested = any(
        token in question_lower for token in ("producto", "más vendido", "mas vendido")
    )
    if top_requested and top_product:
        response_lines.append(
            f"Producto destacado: {top_product.get('product')} con "
            f"{top_product.get('qty', 0)} uds y "
            f"{format_currency(top_product.get('revenue', 0))}."
        )

    sales_requested = any(
        token in question_lower
        for token in ("venta", "ingreso", "total", "facturación", "revenue")
    )
    if sales_requested:
        weekly_change_txt = format_change(weekly.get("change_pct"))
        summary = (
            "Ingresos últimos 7 días: "
            f"{format_currency(weekly.get('total_revenue', 0.0))}"
        )
        if weekly_change_txt:
            summary += f" ({weekly_change_txt} vs semana previa)"
        response_lines.append(summary)
        monthly_change_txt = format_change(monthly.get("change_pct"))
        if monthly_change_txt:
            response_lines.append(
                "Ingresos últimos 30 días: "
                f"{format_currency(monthly.get('total_revenue', 0.0))} "
                f"({monthly_change_txt} vs mes previo)."
            )
        if best_day:
            response_lines.append(
                f"Día más fuerte reciente: {best_day['date']} con "
                f"{format_currency(best_day['revenue'])}."
            )

    total_line = (
        "Acumulado analizado: "
        f"{format_currency(totals.get('revenue', 0.0))} y "
        f"{totals.get('units', 0)} unidades vendidas."
    )
    if total_line not in response_lines:
        response_lines.append(total_line)
    return "\n".join(response_lines)


def generate_chat_response(
    question: str,
    sales_df: pd.DataFrame,
    inventory_rows: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[str, Dict[str, Any]]:
    inventory_rows = inventory_rows or []
    question_norm = normalize_query_text(question)
    insights = compute_chat_insights(sales_df, inventory_rows=inventory_rows)
    smalltalk_answer = answer_chat_smalltalk(question_norm, insights)
    if smalltalk_answer:
        return smalltalk_answer, insights
    custom_answer = handle_custom_chat_request(question, sales_df, inventory_rows)
    answer = compose_chat_answer(question, insights)
    if custom_answer:
        combined = custom_answer.strip()
        if answer:
            combined += "\n\n" + answer
        return combined, insights
    if not is_operational_question(question_norm):
        return build_chat_help_response(insights), insights
    return answer, insights
