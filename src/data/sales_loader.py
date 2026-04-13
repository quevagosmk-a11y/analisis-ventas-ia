# src/data/sales_loader.py
from __future__ import annotations

from typing import Dict, Optional

import pandas as pd

from db import connect as mysql_connect
from utils.numeric import parse_decimal, parse_int


def load_sales_data(csv_path: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path)

    def _parse_numeric_value(raw, allow_decimal: bool) -> float:
        if pd.isna(raw):
            return float("nan")
        try:
            if allow_decimal:
                return float(parse_decimal(raw))
            return float(parse_int(raw))
        except ValueError:
            return float("nan")

    # Normaliza columnas esperadas por Recommender
    # columnas minimas: date, product, category, qty, price, total
    colmap = {
        "fecha": "date",
        "producto": "product",
        "categoria": "category",
        "cantidad": "qty",
        "precio": "price",
        "total_linea": "total",
        "venta_id": "order_id",
        "order_id": "order_id",
        "metodo_pago": "payment_method",
        "payment_method": "payment_method",
        "timestamp": "timestamp",
        "fecha_hora": "timestamp",
        "stock": "stock_on_hand",
        "stock_actual": "stock_on_hand",
        "stock_on_hand": "stock_on_hand",
        "min_stock": "min_stock",
    }
    for source, target in colmap.items():
        if source in df.columns and target not in df.columns:
            df[target] = df[source]
    if "total" not in df.columns and {"qty", "price"}.issubset(df.columns):
        df["total"] = df["qty"] * df["price"]
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
    elif "timestamp" in df.columns:
        df["date"] = pd.to_datetime(df["timestamp"], errors="coerce")
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    else:
        df["timestamp"] = df["date"]
    if "order_id" in df.columns:
        df["order_id"] = df["order_id"].astype(str)

    numeric_map = {
        "qty": True,
        "price": True,
        "total": True,
        "stock_on_hand": False,
        "min_stock": False,
    }
    for col, allow_decimal in numeric_map.items():
        if col in df.columns:
            df[col] = df[col].apply(
                lambda value, flag=allow_decimal: _parse_numeric_value(value, flag)
            )

    required_cols = [col for col in ["qty", "price"] if col in df.columns]
    if required_cols:
        df = df.dropna(subset=required_cols)

    df = df.reset_index(drop=True)

    if "category" not in df.columns:
        df["category"] = "General"
    optional_cols = [
        col
        for col in [
            "order_id",
            "payment_method",
            "timestamp",
            "stock_on_hand",
            "min_stock",
        ]
        if col in df.columns
    ]
    base_cols = ["date", "product", "category", "qty", "price", "total"]
    selected_cols = base_cols + [col for col in optional_cols if col not in base_cols]
    return df[selected_cols].copy()


def load_sales_from_db(
    db_config: Dict[str, str],
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> pd.DataFrame:
    """
    Lee ventas de MySQL y devuelve DataFrame con columnas:
    date, product, category, qty, price, total
    """
    conn = mysql_connect(**db_config)
    try:
        cur = conn.cursor(dictionary=True)
        where = []
        params = []
        where.append("COALESCE(v.anulada, 0)=0")
        if date_from:
            where.append("DATE(v.fecha) >= %s")
            params.append(date_from)
        if date_to:
            where.append("DATE(v.fecha) <= %s")
            params.append(date_to)
        where_sql = ("WHERE " + " AND ".join(where)) if where else ""

        sql = f"""
        SELECT
            v.id                           AS venta_id,
            v.fecha                        AS fecha,
            v.metodo_pago                  AS metodo_pago,
            p.nombre                       AS producto,
            p.categoria                    AS categoria,
            p.stock                        AS stock_actual,
            p.min_stock                    AS min_stock,
            vd.cantidad                    AS cantidad,
            vd.precio                      AS precio,
            (vd.cantidad * vd.precio)      AS total_linea
        FROM ventas v
        JOIN venta_detalle vd ON vd.venta_id = v.id
        JOIN productos p      ON p.id = vd.producto_id
        {where_sql}
        ORDER BY v.fecha DESC
        """
        cur.execute(sql, params)
        rows = cur.fetchall()
        if not rows:
            return pd.DataFrame(
                columns=["date", "product", "category", "qty", "price", "total"]
            )
        df = pd.DataFrame(rows)
        df.rename(
            columns={
                "venta_id": "order_id",
                "fecha": "date",
                "metodo_pago": "payment_method",
                "producto": "product",
                "categoria": "category",
                "stock_actual": "stock_on_hand",
                "min_stock": "min_stock",
                "cantidad": "qty",
                "precio": "price",
                "total_linea": "total",
            },
            inplace=True,
        )
        df["date"] = pd.to_datetime(df["date"])
        df["timestamp"] = df["date"]
        if "order_id" in df.columns:
            df["order_id"] = df["order_id"].astype(str)
        optional_cols = [
            col
            for col in [
                "order_id",
                "payment_method",
                "timestamp",
                "stock_on_hand",
                "min_stock",
            ]
            if col in df.columns
        ]
        base_cols = ["date", "product", "category", "qty", "price", "total"]
        selected_cols = base_cols + [
            col for col in optional_cols if col not in base_cols
        ]
        return df[selected_cols].copy()
    finally:
        conn.close()
