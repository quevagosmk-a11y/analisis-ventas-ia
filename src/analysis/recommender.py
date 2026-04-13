# src/analysis/recommender.py
from __future__ import annotations

from collections import Counter
from itertools import combinations
from typing import Any, Dict, List

import pandas as pd


class Recommender:
    def __init__(self, sales_df: pd.DataFrame):
        # normaliza nombres de columnas esperadas
        df = sales_df.copy()
        cols = {c.lower(): c for c in df.columns}
        # mapea variantes comunes
        rename = {}
        for want in [
            "date",
            "product",
            "category",
            "qty",
            "price",
            "total",
            "order_id",
            "payment_method",
            "timestamp",
        ]:
            if want not in cols:
                # intenta encontrar por prefijos/alias básicos
                for c in df.columns:
                    cl = c.lower()
                    if want in cl:
                        rename[c] = want
                        break
            else:
                rename[cols[want]] = want
        df = df.rename(columns=rename)

        # asegúrate de que existan
        required = {"date", "product", "category", "qty", "price", "total"}
        missing = required - set(df.columns.str.lower())
        if missing:
            raise ValueError(f"Faltan columnas en sales_df: {sorted(missing)}")

        # tipos
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        else:
            df["timestamp"] = df["date"]
        df["timestamp"] = df["timestamp"].fillna(df["date"])
        df["date"] = df["timestamp"].dt.date
        df["qty"] = pd.to_numeric(df["qty"], errors="coerce").fillna(0).astype(int)
        df["price"] = pd.to_numeric(df["price"], errors="coerce").fillna(0.0)
        df["total"] = pd.to_numeric(df["total"], errors="coerce").fillna(
            df["qty"] * df["price"]
        )
        if "order_id" in df.columns:
            df["order_id"] = df["order_id"].astype(str)
        if "payment_method" in df.columns:
            df["payment_method"] = (
                df["payment_method"].fillna("Desconocido").astype(str)
            )

        inventory_cols = []
        if "stock_on_hand" in df.columns:
            df["stock_on_hand"] = pd.to_numeric(df["stock_on_hand"], errors="coerce")
            inventory_cols.append("stock_on_hand")
        if "min_stock" in df.columns:
            df["min_stock"] = pd.to_numeric(df["min_stock"], errors="coerce")
            inventory_cols.append("min_stock")

        self.inventory_by_product: Dict[str, Dict[str, Any]] = {}
        if inventory_cols:
            inventory_view = (
                df[["product"] + inventory_cols]
                .dropna(subset=["product"])
                .drop_duplicates(subset="product", keep="last")
            )
            for _, row in inventory_view.iterrows():
                product_name = row["product"]
                self.inventory_by_product[product_name] = {
                    "stock_on_hand": row.get("stock_on_hand"),
                    "min_stock": row.get("min_stock"),
                }

        self.df = df

    def analyze_sales(self) -> Dict[str, Any]:
        df = self.df

        # Top productos por unidades y por ingresos
        by_prod = (
            df.groupby("product")
            .agg(qty=("qty", "sum"), revenue=("total", "sum"))
            .sort_values(["qty", "revenue"], ascending=False)
        )
        top_product_name = None if by_prod.empty else by_prod.index[0]
        top_row = (
            by_prod.iloc[0].to_dict()
            if not by_prod.empty
            else {"qty": 0, "revenue": 0.0}
        )

        top3 = by_prod.head(3).reset_index()
        top3_list = [
            {
                "product": r["product"],
                "qty": int(r["qty"]),
                "revenue": float(r["revenue"]),
            }
            for _, r in top3.iterrows()
        ]

        # Ingresos diarios
        daily = df.groupby("date")["total"].sum().reset_index().sort_values("date")
        daily_list = [
            {"date": str(r["date"]), "revenue": float(r["total"])}
            for _, r in daily.iterrows()
        ]

        # Reglas simples de ofertas/combo
        offers: List[str] = []
        top_names = set(p["product"] for p in top3_list)
        if any("cerveza" in p.lower() for p in top_names):
            offers.append(
                "Combo cerveza + snack (Papas 30g/105g) con 10% de descuento."
            )
        if (
            "Gaseosa Coca-Cola 400ml" in top_names
            or "Gaseosa Coca-Cola 1.5L" in top_names
        ):
            offers.append("2x1 en gaseosas chicos en horas de calor (3–6 pm).")
        if "Gatorade 500ml" in top_names:
            offers.append("Combo hidratante: Gatorade 500ml + Chocoramo.")
        if "Aguardiente Néctar Verde 750ml" in top_names:
            offers.append(
                "Oferta nocturna: Aguardiente 750ml + 2 Hielos a precio especial."
            )

        combo_suggestions: List[Dict[str, Any]] = []
        if "order_id" in df.columns and df["order_id"].notna().any():
            orders = df.dropna(subset=["order_id"])
            total_orders = orders["order_id"].nunique()
            pair_counter: Counter = Counter()
            revenue_counter: Counter = Counter()
            for _, order in orders.groupby("order_id"):
                products = sorted({str(p) for p in order["product"].dropna()})
                if len(products) < 2 or len(products) > 8:
                    continue
                for a, b in combinations(products, 2):
                    pair_counter[(a, b)] += 1
                    revenue_counter[(a, b)] += float(
                        order.loc[order["product"].isin([a, b]), "total"].sum()
                    )
            for (a, b), count in pair_counter.most_common(5):
                support_pct = (count / total_orders * 100) if total_orders else None
                avg_ticket = revenue_counter[(a, b)] / count if count else 0.0
                combo_suggestions.append(
                    {
                        "items": [a, b],
                        "count": int(count),
                        "support_pct": (
                            None
                            if support_pct is None
                            else float(round(support_pct, 1))
                        ),
                        "avg_ticket": float(round(avg_ticket, 2)),
                    }
                )

        restock_alerts: List[Dict[str, Any]] = []
        if getattr(self, "inventory_by_product", None):
            latest_ts = df["timestamp"].dropna().max()
            if pd.isna(latest_ts):
                latest_ts = pd.Timestamp.utcnow()
            weekly_scope = df[df["timestamp"] >= latest_ts - pd.Timedelta(days=6)]
            weekly_qty = (
                weekly_scope.groupby("product")["qty"].sum()
                if not weekly_scope.empty
                else pd.Series(dtype=float)
            )
            for product_name, info in self.inventory_by_product.items():
                stock_val = info.get("stock_on_hand")
                min_val = info.get("min_stock")
                if stock_val is None or min_val is None:
                    continue
                try:
                    stock_int = int(stock_val)
                    min_int = int(min_val)
                except (TypeError, ValueError):
                    continue
                if min_int < 0:
                    continue
                if stock_int <= min_int:
                    target_stock = max(min_int * 2, min_int + max(3, min_int // 2))
                    recommended = max(target_stock - stock_int, 0)
                    if recommended > 0:
                        restock_alerts.append(
                            {
                                "product": product_name,
                                "stock": stock_int,
                                "min_stock": min_int,
                                "recommended": recommended,
                                "weekly_qty": int(weekly_qty.get(product_name, 0)),
                                "target_stock": target_stock,
                            }
                        )
            if restock_alerts:
                restock_alerts.sort(
                    key=lambda item: (item["stock"], -item["recommended"])
                )
                restock_alerts = restock_alerts[:5]

        return {
            "top_product": {
                "product": top_product_name,
                "qty": int(top_row["qty"]),
                "revenue": float(top_row["revenue"]),
            },
            "top_3_products": top3_list,
            "daily_revenue": daily_list,
            "offer_suggestions": offers,
            "combo_suggestions": combo_suggestions,
            "restock_alerts": restock_alerts,
        }
