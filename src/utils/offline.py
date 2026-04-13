from __future__ import annotations

import json
import os
import threading
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import pandas as pd


def _normalize_text(value: Optional[str]) -> str:
    if not value:
        return ""
    normalized = unicodedata.normalize("NFD", value.lower())
    without_accents = "".join(
        ch for ch in normalized if unicodedata.category(ch) != "Mn"
    )
    return " ".join(without_accents.split())


class OfflineCache:
    """
    Mantiene en memoria una copia serializada de productos y ventas para operar sin conectividad.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._snapshot: Dict[str, Any] = {}
        self.last_loaded: Optional[str] = None
        self.last_path: Optional[str] = None
        self.source: Optional[str] = None
        self.offline: bool = False
        self.last_error: Optional[str] = None

    # region snapshot handling
    def clear(self) -> None:
        with self._lock:
            self._snapshot = {}
            self.last_loaded = None
            self.last_path = None
            self.source = None

    def load_from_file(self, path: str) -> Dict[str, Any]:
        if not os.path.exists(path):
            raise FileNotFoundError(path)
        with open(path, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
        self._set_snapshot(payload, source="file", path=path)
        return payload

    def update(
        self,
        payload: Dict[str, Any],
        *,
        source: str = "live",
        path: Optional[str] = None,
    ) -> None:
        self._set_snapshot(payload, source=source, path=path)

    def _set_snapshot(
        self, payload: Dict[str, Any], *, source: str, path: Optional[str]
    ) -> None:
        with self._lock:
            self._snapshot = payload or {}
            self.last_loaded = (
                self._snapshot.get("created_at") or datetime.utcnow().isoformat()
            )
            self.last_path = path
            self.source = source
            # si logramos cargar, el estado offline se considera resuelto
            self.offline = False
            self.last_error = None

    # endregion

    # region estado
    def mark_offline(self, reason: Optional[str] = None) -> None:
        with self._lock:
            self.offline = True
            if reason:
                self.last_error = reason

    def mark_online(self) -> None:
        with self._lock:
            self.offline = False
            self.last_error = None

    def has_snapshot(self) -> bool:
        with self._lock:
            return bool(self._snapshot)

    def status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "offline": self.offline,
                "last_error": self.last_error,
                "last_loaded": self.last_loaded,
                "last_path": self.last_path,
                "source": self.source,
                "snapshot_available": bool(self._snapshot),
                "productos": len(self._snapshot.get("productos") or []),
                "ventas": len(self._snapshot.get("ventas") or []),
            }

    # endregion

    # region productos
    def get_products(self, search: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._lock:
            productos = list(self._snapshot.get("productos") or [])
        if not productos:
            return []
        if not search:
            return [dict(prod) for prod in productos]
        needle = _normalize_text(search)
        filtered: List[Dict[str, Any]] = []
        for prod in productos:
            haystack = " ".join(
                filter(
                    None,
                    [
                        _normalize_text(str(prod.get("nombre") or "")),
                        _normalize_text(str(prod.get("categoria") or "")),
                    ],
                )
            )
            if needle in haystack:
                filtered.append(dict(prod))
        return filtered

    def get_low_stock_products(self) -> List[Dict[str, Any]]:
        with self._lock:
            productos = list(self._snapshot.get("productos") or [])
        return [
            dict(prod)
            for prod in productos
            if (prod.get("stock") or 0) <= (prod.get("min_stock") or 0)
        ]

    # endregion

    # region ventas helpers
    def _build_sales_dataframe(self) -> Optional[pd.DataFrame]:
        with self._lock:
            ventas = list(self._snapshot.get("ventas") or [])
            detalle = list(self._snapshot.get("venta_detalle") or [])
        if not ventas or not detalle:
            return None
        lookup = {row.get("id"): row for row in ventas}
        rows: List[Dict[str, Any]] = []
        for item in detalle:
            venta_id = item.get("venta_id")
            venta = lookup.get(venta_id)
            if not venta:
                continue
            if bool(venta.get("anulada")):
                continue
            producto = item.get("producto") or item.get("nombre") or item.get("product")
            cantidad = item.get("cantidad") or 0
            precio = item.get("precio") or 0.0
            total = item.get("total")
            if total is None:
                total = float(cantidad) * float(precio)
            rows.append(
                {
                    "venta_id": venta_id,
                    "date": venta.get("fecha"),
                    "product": producto,
                    "qty": float(cantidad),
                    "price": float(precio),
                    "total": float(total),
                    "metodo_pago": venta.get("metodo_pago"),
                    "usuario": venta.get("vendedor"),
                }
            )
        if not rows:
            return None
        df = pd.DataFrame(rows)
        try:
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
        except Exception:
            pass
        return df

    def get_sales_dataframe(self) -> Optional[pd.DataFrame]:
        return self._build_sales_dataframe()

    def get_sales_report(
        self, date_from: datetime, date_to: datetime
    ) -> List[Dict[str, Any]]:
        df = self._build_sales_dataframe()
        if df is None:
            return []
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        mask = (df["date"] >= pd.to_datetime(date_from)) & (
            df["date"] <= pd.to_datetime(date_to) + timedelta(days=1)
        )
        scoped = df.loc[mask]
        grouped = scoped.groupby("venta_id").agg(
            fecha=("date", "max"),
            total=("total", "sum"),
            metodo_pago=("metodo_pago", "first"),
            items=("qty", "sum"),
            vendedor=("usuario", "first"),
        )
        resultados: List[Dict[str, Any]] = []
        for venta_id, row in grouped.iterrows():
            resultados.append(
                {
                    "id": int(venta_id),
                    "fecha": (
                        row["fecha"].isoformat()
                        if isinstance(row["fecha"], datetime)
                        else row["fecha"]
                    ),
                    "total": float(row["total"] or 0.0),
                    "metodo_pago": row.get("metodo_pago"),
                    "items": int(row.get("items") or 0),
                    "vendedor": row.get("vendedor"),
                }
            )
        resultados.sort(key=lambda item: item["fecha"], reverse=True)
        return resultados

    def get_sale_detail(self, sale_id: int) -> Optional[Dict[str, Any]]:
        with self._lock:
            ventas = {row.get("id"): row for row in self._snapshot.get("ventas") or []}
            detalle = [
                dict(item)
                for item in self._snapshot.get("venta_detalle") or []
                if item.get("venta_id") == sale_id
            ]
        venta = ventas.get(sale_id)
        if not venta or not detalle:
            return None
        venta_copy = dict(venta)
        venta_copy["anulada"] = bool(venta_copy.get("anulada"))
        venta_copy["anulacion_autorizada"] = bool(
            venta_copy.get("anulacion_autorizada")
        )
        items: List[Dict[str, Any]] = []
        for item in detalle:
            items.append(
                {
                    "producto_id": item.get("producto_id"),
                    "nombre": item.get("producto"),
                    "cantidad": item.get("cantidad"),
                    "precio": float(item.get("precio") or 0.0),
                    "subtotal": float(
                        item.get("total")
                        or (item.get("precio") or 0.0) * (item.get("cantidad") or 0)
                    ),
                }
            )
        venta_copy["items"] = items
        return venta_copy

    def get_top_products(
        self,
        days: Optional[int] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        df = self._build_sales_dataframe()
        if df is None:
            return []
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        scoped = df
        if date_from and date_to:
            start = pd.to_datetime(date_from, errors="coerce")
            end = pd.to_datetime(date_to, errors="coerce")
            if pd.isna(start) or pd.isna(end):
                return []
            # incluir el dia completo
            end = end + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
            scoped = scoped[(scoped["date"] >= start) & (scoped["date"] <= end)]
        elif days is not None:
            cutoff = pd.Timestamp.utcnow() - pd.Timedelta(days=days)
            scoped = scoped[scoped["date"] >= cutoff]
        if scoped.empty:
            return []
        grouped = scoped.groupby("product").agg(
            cantidad=("qty", "sum"), ingresos=("total", "sum")
        )
        grouped = grouped.sort_values(by="cantidad", ascending=False).head(10)
        resultados: List[Dict[str, Any]] = []
        for product, row in grouped.iterrows():
            resultados.append(
                {
                    "nombre": product,
                    "cantidad": int(round(float(row.get("cantidad") or 0.0))),
                    "ingresos": float(row.get("ingresos") or 0.0),
                }
            )
        return resultados

    def get_dashboard_snapshot(self) -> Optional[Dict[str, Any]]:
        df = self._build_sales_dataframe()
        with self._lock:
            productos = list(self._snapshot.get("productos") or [])
            ventas = list(self._snapshot.get("ventas") or [])
        if df is None or not productos:
            return None
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        today = datetime.utcnow().date()
        ventas_hoy = float(df[df["date"].dt.date == today]["total"].sum())
        stock_bajo = sum(
            1
            for prod in productos
            if (prod.get("stock") or 0) <= (prod.get("min_stock") or 0)
        )
        total_productos = len(productos)
        seven_days = df[df["date"] >= pd.Timestamp(today - timedelta(days=6))]
        pop_counter = Counter()
        for _, row in seven_days.iterrows():
            pop_counter[row.get("product")] += row.get("qty") or 0
        populares = [
            {"nombre": name, "total_vendido": float(qty)}
            for name, qty in pop_counter.most_common(5)
        ]
        payment_counter = defaultdict(lambda: {"total_ventas": 0, "monto_total": 0.0})
        for venta in ventas:
            metodo = venta.get("metodo_pago") or "Desconocido"
            payment_counter[metodo]["total_ventas"] += 1
            payment_counter[metodo]["monto_total"] += float(venta.get("total") or 0.0)
        payment_breakdown = [
            {"metodo_pago": metodo, **values}
            for metodo, values in payment_counter.items()
        ]
        return {
            "ventas_hoy": ventas_hoy,
            "stock_bajo": stock_bajo,
            "total_productos": total_productos,
            "productos_populares": populares,
            "payment_breakdown": payment_breakdown,
            "productos": productos,
        }

    # endregion


OFFLINE_CACHE = OfflineCache()
