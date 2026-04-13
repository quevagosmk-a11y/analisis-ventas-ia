from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - Python < 3.9
    from backports.zoneinfo import ZoneInfo  # type: ignore


BOGOTA_TZ = ZoneInfo("America/Bogota")
DATE_PATTERN = re.compile(
    r"\b(20\d{2})[-/](0?[1-9]|1[0-2])[-/](0?[1-9]|[12][0-9]|3[01])\b"
)


def normalize_query_text(value: str) -> str:
    if not value:
        return ""
    decomposed = unicodedata.normalize("NFD", value.lower())
    stripped = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    cleaned = re.sub(r"[^a-z0-9\s]", " ", stripped)
    return re.sub(r"\s+", " ", cleaned).strip()


def format_currency_basic(value: Optional[float]) -> str:
    try:
        amount = float(value if value is not None else 0.0)
    except (TypeError, ValueError):
        amount = 0.0
    return "${:,.2f}".format(amount)


def build_product_catalog_snapshot(
    inventory_rows: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    for row in inventory_rows:
        name = (row.get("nombre") or "").strip()
        if not name:
            continue
        norm = normalize_query_text(name)
        if not norm:
            continue
        try:
            price = float(row.get("precio") or row.get("price") or 0.0)
        except (TypeError, ValueError):
            price = 0.0
        stock_raw = row.get("stock")
        min_stock_raw = row.get("min_stock")
        try:
            stock_val = int(stock_raw) if stock_raw is not None else None
        except (TypeError, ValueError):
            stock_val = None
        try:
            min_stock_val = int(min_stock_raw) if min_stock_raw is not None else None
        except (TypeError, ValueError):
            min_stock_val = None
        entries.append(
            {
                "id": row.get("id"),
                "name": name,
                "norm": norm,
                "price": price,
                "stock": stock_val,
                "min_stock": min_stock_val,
            }
        )
    return entries


def build_price_lookup_from_sales(sales_df: Optional[pd.DataFrame]) -> Dict[str, float]:
    if sales_df is None or sales_df.empty or "product" not in sales_df.columns:
        return {}
    if "price" not in sales_df.columns:
        return {}
    df = sales_df[["product", "price"]].dropna()
    if df.empty:
        return {}
    if "timestamp" in sales_df.columns:
        df = sales_df.sort_values("timestamp")
        latest = df.groupby("product").tail(1)
    else:
        latest = df.groupby("product")["price"].mean().reset_index()
    lookup: Dict[str, float] = {}
    for _, row in latest.iterrows():
        name = str(row["product"])
        norm = normalize_query_text(name)
        if not norm:
            continue
        try:
            lookup[norm] = float(row["price"])
        except (TypeError, ValueError):
            continue
    return lookup


def _calculate_match_score(product_norm: str, question_norm: str) -> float:
    score = SequenceMatcher(None, product_norm, question_norm).ratio()
    if product_norm in question_norm:
        score = max(score, 0.85 + min(len(product_norm) / 60.0, 0.1))
    product_tokens = product_norm.split()
    question_tokens = set(question_norm.split())
    token_hits = sum(1 for token in product_tokens if token in question_tokens)
    if token_hits:
        score += min(token_hits * 0.05, 0.15)
    return score


def find_products_in_question(
    question_norm: str, catalog: List[Dict[str, Any]], max_items: int = 4
) -> List[Dict[str, Any]]:
    matches: List[Dict[str, Any]] = []
    remaining = question_norm
    for _ in range(max_items):
        best_entry = None
        best_score = 0.55
        for entry in catalog:
            if entry in matches:
                continue
            score = _calculate_match_score(entry["norm"], remaining)
            if score > best_score:
                best_score = score
                best_entry = entry
        if not best_entry:
            break
        matches.append(best_entry)
        remaining = remaining.replace(best_entry["norm"], " ")
    return matches


def _ensure_naive(dt: datetime) -> datetime:
    if dt.tzinfo:
        return dt.astimezone(BOGOTA_TZ).replace(tzinfo=None)
    return dt


def resolve_period(
    question_norm: str, *, today: Optional[datetime] = None
) -> Tuple[datetime, datetime, str]:
    ref = today or datetime.now(BOGOTA_TZ)
    ref = ref.replace(hour=0, minute=0, second=0, microsecond=0)
    matched = DATE_PATTERN.search(question_norm)
    if matched:
        year, month, day = map(int, matched.groups())
        start = ref.replace(year=year, month=month, day=day)
        end = start + timedelta(days=1)
        return _ensure_naive(start), _ensure_naive(end), start.date().isoformat()
    if "ayer" in question_norm:
        start = ref - timedelta(days=1)
        end = start + timedelta(days=1)
        return _ensure_naive(start), _ensure_naive(end), "ayer"
    if "hoy" in question_norm:
        start = ref
        end = ref + timedelta(days=1)
        return _ensure_naive(start), _ensure_naive(end), "hoy"
    if "mes" in question_norm or "30 dias" in question_norm:
        start = ref - timedelta(days=30)
        return (
            _ensure_naive(start),
            _ensure_naive(ref + timedelta(days=1)),
            "ultimo mes",
        )
    if "fin de semana" in question_norm:
        weekday = ref.weekday()
        start = ref - timedelta(days=(weekday + 2) % 7)
        return (
            _ensure_naive(start),
            _ensure_naive(start + timedelta(days=3)),
            "fin de semana pasado",
        )
    if "semana pasada" in question_norm:
        start = ref - timedelta(days=14)
        end = start + timedelta(days=7)
        return _ensure_naive(start), _ensure_naive(end), "semana pasada"
    if "semana" in question_norm or "7 dias" in question_norm:
        start = ref - timedelta(days=7)
        return (
            _ensure_naive(start),
            _ensure_naive(ref + timedelta(days=1)),
            "ultima semana",
        )
    return (
        _ensure_naive(ref - timedelta(days=7)),
        _ensure_naive(ref + timedelta(days=1)),
        "ultima semana",
    )


def answer_sales_summary(
    question_norm: str, sales_df: Optional[pd.DataFrame], catalog: List[Dict[str, Any]]
) -> Optional[str]:
    if sales_df is None or sales_df.empty:
        return None
    tokens = set(question_norm.split())
    keywords = {
        "ventas",
        "venta",
        "vendi",
        "vendiste",
        "vendido",
        "ingreso",
        "ingresos",
        "facture",
        "facturacion",
        "factura",
    }
    amount_words = {
        "cuanto",
        "cuanta",
        "cuantas",
        "cuantos",
        "cunato",
        "cunata",
        "cunatos",
        "cunatas",
        "total",
        "suma",
        "ganancia",
        "gane",
        "cantidad",
        "cantidades",
    }
    if not (keywords.intersection(tokens) and amount_words.intersection(tokens)):
        return None
    period_start, period_end, label = resolve_period(question_norm)
    df = sales_df.copy()
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    else:
        df["timestamp"] = pd.to_datetime(df["date"], errors="coerce")
    mask = (df["timestamp"] >= period_start) & (df["timestamp"] < period_end)
    period_df = df.loc[mask]
    if period_df.empty:
        return f"No tengo ventas registradas para {label}."
    matches = find_products_in_question(question_norm, catalog, max_items=3)
    if matches:
        names = [entry["name"] for entry in matches]
        period_df = period_df[period_df["product"].isin(names)]
        if period_df.empty:
            return f"No hay ventas registradas para {', '.join(names)} en {label}."
    revenue = float(period_df["total"].sum())
    units = int(period_df["qty"].sum())
    detail_parts = []
    top_products = (
        period_df.groupby("product")["qty"].sum().sort_values(ascending=False).head(3)
    )
    for product, qty in top_products.items():
        detail_parts.append(f"- {product}: {qty} unidades")
    summary = (
        f"En {label} registraste {units} unidades por {format_currency_basic(revenue)}."
    )
    if matches:
        summary = (
            f"En {label}, vendiste {units} unidades "
            f"({format_currency_basic(revenue)}) de "
            f"{', '.join(set(period_df['product']))}."
        )
    if detail_parts:
        summary += " Productos destacados:\n" + "\n".join(detail_parts)
    return summary


def answer_restock_question(
    question_norm: str, catalog: List[Dict[str, Any]]
) -> Optional[str]:
    keywords = {
        "reponer",
        "reposicion",
        "agotando",
        "agotado",
        "stock",
        "comprar",
        "pedido",
        "pedir",
    }
    tokens = set(question_norm.split())
    if not keywords.intersection(tokens):
        return None
    if not catalog:
        return None
    matches = find_products_in_question(question_norm, catalog, max_items=3)
    low_stock_items = [
        entry
        for entry in catalog
        if entry.get("stock") is not None
        and entry.get("min_stock") is not None
        and entry["stock"] <= entry["min_stock"]
    ]
    low_stock_items.sort(key=lambda item: (item["stock"], item["min_stock"]))
    if matches:
        lines = []
        for entry in matches:
            stock = entry.get("stock")
            min_stock = entry.get("min_stock")
            if stock is None or min_stock is None:
                lines.append(f"No tengo stock minimo registrado para {entry['name']}.")
                continue
            if stock <= min_stock:
                sugerido = max(min_stock * 2 - stock, min_stock or 5)
                lines.append(
                    f"{entry['name']} tiene {stock} unidades (minimo {min_stock}). "
                    f"Recomiendo reponer {sugerido} unidades."
                )
            else:
                lines.append(
                    f"{entry['name']} tiene {stock} unidades disponibles, aun por "
                    f"encima del minimo ({min_stock})."
                )
        return "\n".join(lines)
    if not low_stock_items:
        return (
            "No veo productos con stock critico ahora mismo. Puedes revisar el "
            "inventario para confirmar."
        )
    top_alerts = low_stock_items[:3]
    response = ["Los productos mas urgentes para reponer son:"]
    for entry in top_alerts:
        stock = entry.get("stock") or 0
        min_stock = entry.get("min_stock") or 0
        sugerido = max(min_stock * 2 - stock, min_stock or 5)
        response.append(
            f"- {entry['name']}: stock {stock} (min {min_stock}). Reponer "
            f"alrededor de {sugerido} unidades."
        )
    return "\n".join(response)


def answer_top_products_question(
    question_norm: str, sales_df: Optional[pd.DataFrame]
) -> Optional[str]:
    if sales_df is None or sales_df.empty:
        return None
    keywords = {
        "top",
        "mejor",
        "mejores",
        "popular",
        "populares",
        "mas",
        "vendido",
        "vendidos",
        "ranking",
        "top5",
        "top3",
    }
    if not any(word in question_norm for word in keywords):
        return None
    period_start, period_end, label = resolve_period(question_norm)
    df = sales_df.copy()
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    else:
        df["timestamp"] = pd.to_datetime(df["date"], errors="coerce")
    mask = (df["timestamp"] >= period_start) & (df["timestamp"] < period_end)
    period_df = df.loc[mask]
    if period_df.empty:
        return f"No tengo ventas registradas para {label}."
    match = re.search(r"top\s*(\d+)", question_norm)
    count = int(match.group(1)) if match else 3
    count = max(1, min(count, 10))
    top = (
        period_df.groupby("product")["qty"]
        .sum()
        .sort_values(ascending=False)
        .head(count)
    )
    if top.empty:
        return f"No hay ventas suficientes para calcular el top en {label}."
    lines = [f"Top {len(top)} productos en {label}:"]
    for idx, (product, qty) in enumerate(top.items(), start=1):
        revenue = float(period_df[period_df["product"] == product]["total"].sum())
        lines.append(
            f"{idx}. {product} - {qty} unidades ({format_currency_basic(revenue)})"
        )
    return "\n".join(lines)


def answer_payment_method_question(
    question_norm: str, sales_df: Optional[pd.DataFrame]
) -> Optional[str]:
    if sales_df is None or sales_df.empty:
        return None
    tokens = set(question_norm.split())
    keywords = {
        "pago",
        "pagos",
        "metodo",
        "metodos",
        "efectivo",
        "nequi",
        "daviplata",
        "tarjeta",
        "transferencia",
        "cobro",
    }
    if not keywords.intersection(tokens):
        return None
    period_start, period_end, label = resolve_period(question_norm)
    df = sales_df.copy()
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    else:
        df["timestamp"] = pd.to_datetime(df["date"], errors="coerce")
    mask = (df["timestamp"] >= period_start) & (df["timestamp"] < period_end)
    period_df = df.loc[mask]
    if period_df.empty:
        return f"No tengo pagos registrados para {label}."
    period_df["payment_method"] = period_df.get("payment_method", "Desconocido").fillna(
        "Desconocido"
    )
    grouped = (
        period_df.groupby("payment_method")["total"].sum().sort_values(ascending=False)
    )
    total = float(grouped.sum())
    lines = [
        f"Distribucion de metodos de pago en {label} "
        f"(total {format_currency_basic(total)}):"
    ]
    for method, amount in grouped.items():
        percentage = (amount / total * 100) if total > 0 else 0
        lines.append(
            f"- {method}: {format_currency_basic(amount)} ({percentage:.1f}%)"
        )
    return "\n".join(lines)


def is_stock_question(question_norm: str) -> bool:
    tokens = question_norm.split()
    keywords = {"stock", "inventario", "disponible", "quedan", "queda", "restante"}
    quantifiers = {"cuanta", "cuanto", "cuantos", "cuantas"}
    if keywords.intersection(tokens):
        return True
    if quantifiers.intersection(tokens) and any(
        key in tokens for key in ("queda", "quedan", "disponible")
    ):
        return True
    return False


def is_combo_question(question_norm: str) -> bool:
    tokens = question_norm.split()
    combo_words = {
        "combo",
        "combinacion",
        "combina",
        "junto",
        "mezcla",
        "arma",
        "armame",
    }
    price_words = {"precio", "cuesta", "vale", "total", "costo"}
    return (combo_words.intersection(tokens) and price_words.intersection(tokens)) or (
        "combo" in tokens
    )


def answer_stock_query(
    question_norm: str, catalog: List[Dict[str, Any]]
) -> Optional[str]:
    if not catalog or not is_stock_question(question_norm):
        return None
    matches = find_products_in_question(question_norm, catalog, max_items=1)
    if not matches:
        return None
    entry = matches[0]
    stock_val = entry.get("stock")
    if stock_val is None:
        return f"No tengo stock registrado para {entry['name']}."
    message = f"Actualmente hay {stock_val} unidades de {entry['name']}."
    min_stock = entry.get("min_stock")
    if min_stock is not None and stock_val <= min_stock:
        message += " Advertencia: el stock esta en o por debajo del minimo configurado."
    return message


def answer_combo_query(
    question_norm: str, catalog: List[Dict[str, Any]], price_lookup: Dict[str, float]
) -> Optional[str]:
    if not catalog or not is_combo_question(question_norm):
        return None
    matches = find_products_in_question(question_norm, catalog, max_items=4)
    if len(matches) < 2:
        return None
    total_price = 0.0
    missing_price = False
    detail_lines = []
    used_names = []
    for entry in matches:
        norm_name = entry["norm"]
        price = entry.get("price") or price_lookup.get(norm_name)
        if price is None or price == 0:
            missing_price = True
            detail_lines.append(f"- {entry['name']}: sin precio registrado")
        else:
            total_price += float(price)
            detail_lines.append(f"- {entry['name']}: {format_currency_basic(price)}")
        used_names.append(entry["name"])
    if missing_price and total_price == 0.0:
        return "No tengo precios suficientes para calcular ese combo en este momento."
    response = []
    combo_title = " + ".join(used_names[:3])
    response.append(f"Combo sugerido: {combo_title}.")
    response.extend(detail_lines)
    if not missing_price:
        response.append(
            f"Precio aproximado del combo: {format_currency_basic(total_price)}."
        )
    else:
        response.append(
            "Subtotal disponible: "
            f"{format_currency_basic(total_price)} (algunos precios faltan)."
        )
    return "\n".join(response)


def handle_custom_chat_request(
    question: str,
    sales_df: Optional[pd.DataFrame],
    inventory_rows: List[Dict[str, Any]],
) -> Optional[str]:
    question_norm = normalize_query_text(question)
    if not question_norm:
        return None
    catalog = build_product_catalog_snapshot(inventory_rows)
    if not catalog:
        return None
    price_lookup = build_price_lookup_from_sales(sales_df)
    stock_answer = answer_stock_query(question_norm, catalog)
    if stock_answer:
        return stock_answer
    combo_answer = answer_combo_query(question_norm, catalog, price_lookup)
    if combo_answer:
        return combo_answer
    sales_answer = answer_sales_summary(question_norm, sales_df, catalog)
    if sales_answer:
        return sales_answer
    restock_answer = answer_restock_question(question_norm, catalog)
    if restock_answer:
        return restock_answer
    top_products_answer = answer_top_products_question(question_norm, sales_df)
    if top_products_answer:
        return top_products_answer
    payment_answer = answer_payment_method_question(question_norm, sales_df)
    if payment_answer:
        return payment_answer
    return None
