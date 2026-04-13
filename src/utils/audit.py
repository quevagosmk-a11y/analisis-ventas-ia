from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional


def _to_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _label_state(value: Any) -> str:
    normalized = str(value or "").strip().lower().replace(" ", "_")
    labels = {
        "cargada": "con imagen",
        "sin_imagen": "sin imagen",
        "sinimagen": "sin imagen",
        "ninguna": "sin imagen",
        "none": "sin imagen",
    }
    if normalized in labels:
        return labels[normalized]
    if not normalized:
        return "-"
    return normalized.replace("_", " ")


def _format_percentage(value: Any) -> str:
    parsed = _to_float(value)
    if parsed is None:
        return "0%"
    rounded = round(parsed, 2)
    if abs(rounded - round(rounded)) < 0.0001:
        return f"{int(round(rounded))}%"
    return f"{rounded:.2f}%"


def _default_currency_formatter(value: Optional[float]) -> str:
    try:
        amount = float(value if value is not None else 0.0)
    except (TypeError, ValueError):
        amount = 0.0
    rounded = int(round(amount))
    sign = "-" if rounded < 0 else ""
    integer = f"{abs(rounded):,}".replace(",", ".")
    return f"{sign}${integer}"


def _format_product_changes(
    details: Optional[Dict[str, Any]],
    *,
    currency_formatter: Callable[[Optional[float]], str],
) -> List[str]:
    if not isinstance(details, dict):
        return []
    changes: List[str] = []
    name_change = (
        details.get("nombre") if isinstance(details.get("nombre"), dict) else {}
    )
    category_change = (
        details.get("categoria") if isinstance(details.get("categoria"), dict) else {}
    )
    price_change = (
        details.get("precio") if isinstance(details.get("precio"), dict) else {}
    )
    iva_change = (
        details.get("iva_percent")
        if isinstance(details.get("iva_percent"), dict)
        else {}
    )
    stock_change = (
        details.get("stock") if isinstance(details.get("stock"), dict) else {}
    )
    min_stock_change = (
        details.get("min_stock") if isinstance(details.get("min_stock"), dict) else {}
    )
    image_change = (
        details.get("imagen") if isinstance(details.get("imagen"), dict) else {}
    )

    if name_change and name_change.get("before") != name_change.get("after"):
        changes.append(
            f'Nombre: "{name_change.get("before") or "-"}" -> "{name_change.get("after") or "-"}"'
        )
    if category_change and category_change.get("before") != category_change.get(
        "after"
    ):
        changes.append(
            f'Categoria: {category_change.get("before") or "-"} -> {category_change.get("after") or "-"}'
        )

    old_price = _to_float(price_change.get("before"))
    new_price = _to_float(price_change.get("after"))
    if old_price is not None and new_price is not None and old_price != new_price:
        changes.append(
            f"Precio: {currency_formatter(old_price)} -> {currency_formatter(new_price)}"
        )

    old_iva = iva_change.get("before")
    new_iva = iva_change.get("after")
    if old_iva is not None and new_iva is not None and old_iva != new_iva:
        changes.append(
            f"IVA: {_format_percentage(old_iva)} -> {_format_percentage(new_iva)}"
        )

    old_stock = _to_float(stock_change.get("before"))
    new_stock = _to_float(stock_change.get("after"))
    if old_stock is not None and new_stock is not None and old_stock != new_stock:
        changes.append(f"Stock: {int(round(old_stock))} -> {int(round(new_stock))}")

    old_min = _to_float(min_stock_change.get("before"))
    new_min = _to_float(min_stock_change.get("after"))
    if old_min is not None and new_min is not None and old_min != new_min:
        changes.append(f"Minimo: {int(round(old_min))} -> {int(round(new_min))}")

    if image_change:
        action = str(image_change.get("action") or "").strip().lower()
        before_state = _label_state(image_change.get("before"))
        after_state = _label_state(image_change.get("after"))
        if action == "reemplazada":
            changes.append("Imagen: reemplazada")
        elif before_state != after_state and before_state != "-" and after_state != "-":
            changes.append(f"Imagen: {before_state} -> {after_state}")
        elif before_state != "-" and after_state == "-":
            changes.append(f"Imagen: {before_state} -> sin imagen")
        elif before_state == "-" and after_state != "-":
            changes.append(f"Imagen: sin imagen -> {after_state}")
        elif (
            image_change.get("before_hash")
            and image_change.get("after_hash")
            and image_change.get("before_hash") != image_change.get("after_hash")
        ):
            changes.append("Imagen: contenido actualizado")
        before_mime = str(image_change.get("before_mime") or "").strip().lower()
        after_mime = str(image_change.get("after_mime") or "").strip().lower()
        if before_mime and after_mime and before_mime != after_mime:
            changes.append(f"Formato imagen: {before_mime} -> {after_mime}")
    return changes


def build_product_update_audit_description(
    product_name: Optional[str],
    details: Optional[Dict[str, Any]],
    *,
    currency_formatter: Optional[Callable[[Optional[float]], str]] = None,
) -> str:
    normalized_name = str(product_name or "").strip() or "producto"
    header = f'Producto "{normalized_name}" actualizado'
    formatter = currency_formatter or _default_currency_formatter
    changes = _format_product_changes(details, currency_formatter=formatter)
    if not changes:
        return header[:255]
    preview = changes[:3]
    pending = len(changes) - len(preview)
    if pending > 0:
        preview.append(f"+{pending} cambio(s)")
    return f'{header}: {" | ".join(preview)}'[:255]
