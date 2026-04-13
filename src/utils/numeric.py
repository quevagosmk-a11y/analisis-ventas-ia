from __future__ import annotations

import math
import re
from decimal import Decimal, InvalidOperation
from typing import Any

_ALLOWED_CURRENCY_TOKENS = ("COP", "COL", "USD", "CRC", "GTQ", "MXN", "PEN")

_THOUSAND_SPLIT_RE = re.compile(r"[.,]")


def _looks_like_thousands(parts: list[str]) -> bool:
    if len(parts) <= 1:
        return False
    if not all(part.isdigit() for part in parts):
        return False
    return all(len(part) == 3 for part in parts[1:]) and 1 <= len(parts[0]) <= 3


def _strip_currency_tokens(value: str) -> str:
    text = value
    for token in _ALLOWED_CURRENCY_TOKENS:
        text = re.sub(token, "", text, flags=re.IGNORECASE)
    text = text.replace("$", "")
    return text


def normalize_numeric_string(value: Any, *, allow_decimal: bool) -> str:
    """Normalize user-provided numeric input into a canonical ASCII string."""
    if value is None:
        raise ValueError("Valor numerico requerido")
    if isinstance(value, bool):
        raise ValueError("Valor numerico invalido")
    if isinstance(value, Decimal):
        text = format(value, "f")
    elif isinstance(value, (int, float)):
        if isinstance(value, float):
            if not math.isfinite(value):
                raise ValueError("Valor numerico invalido")
            text = format(value, ".15g")
        else:
            text = str(value)
    elif isinstance(value, str):
        text = value
    else:
        text = str(value)
    text = text.strip()
    if not text:
        raise ValueError("Valor numerico requerido")
    text = text.replace("\u00a0", "").replace(" ", "")
    text = _strip_currency_tokens(text)
    text = text.replace("'", "")
    if not text:
        raise ValueError("Valor numerico requerido")
    sign = ""
    if text[0] in "+-":
        sign = "-" if text[0] == "-" else ""
        text = text[1:]
    if not text:
        raise ValueError("Valor numerico invalido")
    if re.search(r"[A-Za-z]", text):
        raise ValueError("Valor numerico invalido")
    if re.search(r"[+-]", text):
        raise ValueError("Valor numerico invalido")
    if allow_decimal:
        if "," in text and "." in text:
            last_comma = text.rfind(",")
            last_dot = text.rfind(".")
            if last_comma > last_dot:
                decimal_sep = ","
                thousands_sep = "."
            else:
                decimal_sep = "."
                thousands_sep = ","
            text = text.replace(thousands_sep, "")
            text = text.replace(decimal_sep, ".")
        elif "," in text:
            parts = text.split(",")
            if len(parts) == 2 and parts[1].isdigit() and 1 <= len(parts[1]) <= 2:
                text = ".".join(parts)
            elif _looks_like_thousands(parts):
                text = "".join(parts)
            else:
                raise ValueError("Valor numerico invalido")
        elif "." in text:
            parts = text.split(".")
            if len(parts) == 2 and parts[1].isdigit() and 1 <= len(parts[1]) <= 2:
                text = ".".join(parts)
            elif _looks_like_thousands(parts):
                text = "".join(parts)
            elif len(parts) > 2:
                raise ValueError("Valor numerico invalido")
            else:
                text = ".".join(parts)
        else:
            if not text.isdigit():
                raise ValueError("Valor numerico invalido")
    else:
        if "," in text or "." in text:
            parts = re.split(_THOUSAND_SPLIT_RE, text)
            if not all(part.isdigit() for part in parts):
                raise ValueError("Valor numerico invalido")
            text = "".join(parts)
        if not text.isdigit():
            raise ValueError("Valor numerico invalido")
    if not text:
        raise ValueError("Valor numerico invalido")
    normalized = sign + text
    if not normalized or normalized in {"+", "-"}:
        raise ValueError("Valor numerico invalido")
    return normalized


def parse_decimal(value: Any) -> Decimal:
    normalized = normalize_numeric_string(value, allow_decimal=True)
    try:
        dec = Decimal(normalized)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("Valor numerico invalido") from exc
    if dec.is_nan() or dec.is_infinite():
        raise ValueError("Valor numerico invalido")
    return dec


def parse_int(value: Any) -> int:
    dec = parse_decimal(value)
    if dec != dec.to_integral_value():
        raise ValueError("Valor numerico invalido")
    return int(dec)


__all__ = [
    "normalize_numeric_string",
    "parse_decimal",
    "parse_int",
]
