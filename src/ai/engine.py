from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pandas as pd

from .features import build_latest_features
from .model import get_demand_model_bundle


@dataclass
class AIEngineConfig:
    window_days: int = 30
    horizon_days: int = 14
    max_alerts: int = 10
    min_rotation_threshold: float = 0.05  # unidades por dia
    high_rotation_threshold: float = 0.5


def _normalize_sales_df(raw_df: Optional[pd.DataFrame]) -> pd.DataFrame:
    if raw_df is None or raw_df.empty:
        return pd.DataFrame(columns=["date", "product", "qty", "price", "total"])
    df = raw_df.copy()
    if "date" not in df.columns:
        if "timestamp" in df.columns:
            df["date"] = pd.to_datetime(df["timestamp"], errors="coerce")
        else:
            raise ValueError("El dataframe de ventas no incluye columna 'date'")
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])
    df["product"] = df["product"].fillna("Producto sin nombre")
    df["qty"] = pd.to_numeric(df["qty"], errors="coerce").fillna(0)
    if "total" not in df.columns:
        if {"qty", "price"}.issubset(df.columns):
            df["total"] = (
                pd.to_numeric(df["price"], errors="coerce").fillna(0) * df["qty"]
            )
        else:
            df["total"] = df["qty"]
    df["total"] = pd.to_numeric(df["total"], errors="coerce").fillna(0)
    return df


def _normalize_inventory(rows: Optional[Sequence[Dict[str, Any]]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=["product", "stock", "min_stock", "categoria"])
    df = pd.DataFrame(rows)
    df.rename(
        columns={
            "nombre": "product",
            "stock_actual": "stock",
            "stock": "stock",
            "min_stock": "min_stock",
            "categoria": "categoria",
        },
        inplace=True,
    )
    df["product"] = df["product"].fillna("Producto sin nombre")
    df["stock"] = pd.to_numeric(df["stock"], errors="coerce").fillna(0).astype(int)
    df["min_stock"] = (
        pd.to_numeric(df["min_stock"], errors="coerce").fillna(0).astype(int)
    )
    if "categoria" not in df.columns:
        df["categoria"] = ""
    return df[["product", "stock", "min_stock", "categoria"]].copy()


def _rotation_summary(
    sales_df: pd.DataFrame, today: datetime, config: AIEngineConfig
) -> pd.DataFrame:
    if sales_df.empty:
        return pd.DataFrame(columns=["product", "avg_daily", "qty_window"])
    window_start = today - timedelta(days=config.window_days)
    mask = sales_df["date"] >= window_start
    window_df = sales_df.loc[mask]
    if window_df.empty:
        return pd.DataFrame(columns=["product", "avg_daily", "qty_window"])
    grouped = window_df.groupby("product")["qty"].sum().reset_index(name="qty_window")
    grouped["avg_daily"] = grouped["qty_window"] / max(config.window_days, 1)
    return grouped


def _calculate_trends(sales_df: pd.DataFrame, today: datetime) -> List[Dict[str, Any]]:
    if sales_df.empty:
        return []
    current_start = today - timedelta(days=7)
    previous_start = today - timedelta(days=14)
    current_df = sales_df[sales_df["date"] >= current_start]
    previous_df = sales_df[
        (sales_df["date"] < current_start) & (sales_df["date"] >= previous_start)
    ]
    if current_df.empty:
        return []
    current_totals = current_df.groupby("product")["qty"].sum()
    previous_totals = previous_df.groupby("product")["qty"].sum()
    trends: List[Dict[str, Any]] = []
    for product, qty_now in current_totals.sort_values(ascending=False).items():
        qty_prev = previous_totals.get(product, 0)
        if qty_prev == 0 and qty_now == 0:
            continue
        if qty_prev == 0:
            variation = 1.0
        else:
            variation = (qty_now - qty_prev) / qty_prev
        if abs(variation) < 0.1 and qty_now < 2:
            continue
        variation_pct = f"{variation:+.0%}"
        trends.append(
            {
                "producto": product,
                "variacion_ventas": variation_pct,
                "unidades_actuales": float(qty_now),
            }
        )
        if len(trends) >= 8:
            break
    return trends


def _suggest_restock(
    stock: int, min_stock: int, avg_daily: float, config: AIEngineConfig
) -> int:
    horizon_need = math.ceil(avg_daily * config.horizon_days)
    target_stock = max(min_stock * 2, horizon_need)
    suggestion = max(target_stock - stock, 0)
    return int(suggestion)


def _compile_high_rotation(
    rotation_df: pd.DataFrame,
    inventory_df: pd.DataFrame,
    config: AIEngineConfig,
    predictions: Optional[Dict[str, Dict[str, Any]]] = None,
    prediction_meta: Optional[Dict[str, Any]] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    if rotation_df.empty:
        return [], []
    merged = rotation_df.merge(inventory_df, how="left", on="product")
    merged["stock"] = (
        pd.to_numeric(merged.get("stock"), errors="coerce").fillna(0).astype(int)
    )
    merged["min_stock"] = (
        pd.to_numeric(merged.get("min_stock"), errors="coerce").fillna(0).astype(int)
    )
    if "categoria" in merged.columns:
        merged["categoria"] = merged["categoria"].fillna("")
    else:
        merged["categoria"] = ""

    positive = merged[merged["avg_daily"] > 0].sort_values(
        by="avg_daily", ascending=False
    )
    candidates = positive
    if config.high_rotation_threshold > 0:
        thresholded = positive[positive["avg_daily"] >= config.high_rotation_threshold]
        if not thresholded.empty:
            candidates = thresholded
    top_rows = candidates.head(config.max_alerts)
    predictions = predictions or {}
    pred_horizon = (
        int(prediction_meta.get("horizon_days"))
        if prediction_meta and prediction_meta.get("horizon_days")
        else config.horizon_days
    )

    high_rotation: List[Dict[str, Any]] = []
    restock: List[Dict[str, Any]] = []
    for _, row in top_rows.iterrows():
        avg_daily = float(row.get("avg_daily", 0.0) or 0.0)
        qty_window = int(row.get("qty_window", 0) or 0)
        stock = int(row.get("stock", 0) or 0)
        min_stock = int(row.get("min_stock", 0) or 0)
        categoria = str(row.get("categoria", "") or "")
        dias_cobertura = None
        if avg_daily > 0:
            dias_cobertura = round(stock / avg_daily, 1) if stock > 0 else 0.0
        demand_info = predictions.get(row["product"])
        predicted_total = None
        if demand_info:
            predicted_total = max(
                float(demand_info.get("predicted_demand", 0.0) or 0.0), 0.0
            )
            predicted_avg = predicted_total / max(pred_horizon, 1)
            avg_daily = max(avg_daily, predicted_avg)
            if predicted_avg > 0:
                dias_cobertura = round(stock / predicted_avg, 1) if stock > 0 else 0.0
        sugerido = _suggest_restock(stock, min_stock, avg_daily, config)
        if predicted_total is not None:
            sugerido = max(sugerido, int(max(math.ceil(predicted_total) - stock, 0)))
        entry = {
            "producto": row.get("product", ""),
            "promedio_diario": round(avg_daily, 2),
            "unidades_periodo": qty_window,
            "stock_actual": stock,
            "stock_minimo": min_stock,
            "dias_cobertura": dias_cobertura,
            "categoria": categoria,
            "compra_sugerida": int(sugerido),
            "prediccion_horizonte": predicted_total,
            "horizonte_modelo": pred_horizon if predicted_total is not None else None,
        }
        high_rotation.append(entry)
        if sugerido > 0:
            comentario = f"Sugerido comprar {sugerido} unidades para cubrir las proximas {pred_horizon if predicted_total is not None else config.horizon_days} dias."
            restock_entry = entry.copy()
            restock_entry["comentario"] = comentario
            restock.append(restock_entry)
    return high_rotation, restock


def generate_ai_report(
    sales_df: Optional[pd.DataFrame],
    inventory_rows: Optional[Sequence[Dict[str, Any]]],
    *,
    restock_rows: Optional[pd.DataFrame] = None,
    today: Optional[datetime] = None,
    config: Optional[AIEngineConfig] = None,
) -> Dict[str, Any]:
    """
    Genera un reporte analitico con alertas y tendencias usando unicamente datos locales.
    """
    cfg = config or AIEngineConfig()
    ref_date = today or datetime.now()
    norm_sales = _normalize_sales_df(sales_df)
    if not norm_sales.empty:
        latest_sale = norm_sales["date"].max()
        if pd.notna(latest_sale):
            latest_sale = (
                latest_sale.to_pydatetime()
                if hasattr(latest_sale, "to_pydatetime")
                else latest_sale
            )
            if (ref_date - latest_sale).days > cfg.window_days:
                ref_date = latest_sale
    inventory_df = _normalize_inventory(inventory_rows)
    rotation_df = _rotation_summary(norm_sales, ref_date, cfg)

    demand_predictions: Dict[str, Dict[str, Any]] = {}
    prediction_meta: Dict[str, Any] = {}
    prediction_strategy = "heuristica_promedio"
    model_bundle = get_demand_model_bundle()
    if model_bundle:
        model = model_bundle.get("model")
        bundle_meta = model_bundle.get("metadata") or {}
        feature_columns = bundle_meta.get("feature_columns") or []
        window_for_model = int(bundle_meta.get("window_days") or cfg.window_days)
        horizon_for_model = int(bundle_meta.get("horizon_days") or cfg.horizon_days)
        if model and feature_columns:
            features_df = build_latest_features(
                norm_sales,
                window_days=window_for_model,
                horizon_days=horizon_for_model,
            )
            if not features_df.empty and all(
                col in features_df.columns for col in feature_columns
            ):
                try:
                    feature_matrix = (
                        features_df[feature_columns].fillna(0.0).to_numpy(dtype=float)
                    )
                    preds = model.predict(feature_matrix)
                    feature_rows = features_df.assign(
                        predicted_demand=[max(float(p), 0.0) for p in preds]
                    )
                    demand_predictions = {
                        row["product"]: {
                            "predicted_demand": float(row["predicted_demand"]),
                            "feature_date": (
                                row["feature_date"].isoformat()
                                if hasattr(row["feature_date"], "isoformat")
                                else str(row["feature_date"])
                            ),
                        }
                        for _, row in feature_rows.iterrows()
                    }
                    prediction_meta = {
                        "horizon_days": horizon_for_model,
                        "window_days": window_for_model,
                        "feature_columns": feature_columns,
                        "trained_at": bundle_meta.get("trained_at"),
                        "mae": bundle_meta.get("mae"),
                        "rmse": bundle_meta.get("rmse"),
                        "mape": bundle_meta.get("mape"),
                    }
                    prediction_strategy = "modelo_entrenado"
                except Exception as exc:
                    print(f"[ia] error generando predicciones de demanda: {exc}")

    # Fallback: prediccion estadistica por promedio diario cuando no existe modelo entrenado.
    if not demand_predictions and not norm_sales.empty:
        horizon = cfg.horizon_days
        window_start = ref_date - timedelta(days=cfg.window_days)
        scope = norm_sales[norm_sales["date"] >= window_start]
        observation_days = max(cfg.window_days, 1)
        if scope.empty:
            scope = norm_sales
            min_date = pd.to_datetime(scope["date"], errors="coerce").min()
            max_date = pd.to_datetime(scope["date"], errors="coerce").max()
            if pd.notna(min_date) and pd.notna(max_date):
                observation_days = max(1, int((max_date - min_date).days) + 1)

        grouped_recent = scope.groupby("product")["qty"].sum()
        grouped_history = norm_sales.groupby("product")["qty"].sum()
        history_min_date = pd.to_datetime(norm_sales["date"], errors="coerce").min()
        history_max_date = pd.to_datetime(norm_sales["date"], errors="coerce").max()
        history_days = max(cfg.window_days, 1)
        if pd.notna(history_min_date) and pd.notna(history_max_date):
            history_days = max(1, int((history_max_date - history_min_date).days) + 1)

        for product in grouped_history.index:
            if product in grouped_recent.index:
                avg_daily = float(grouped_recent[product]) / max(observation_days, 1)
            else:
                avg_daily = float(grouped_history[product]) / max(history_days, 1)
            predicted_total = max(avg_daily * horizon, 0.0)
            demand_predictions[str(product)] = {
                "predicted_demand": float(round(predicted_total, 2)),
                "feature_date": ref_date.date().isoformat(),
            }
        prediction_meta = {
            "horizon_days": horizon,
            "window_days": cfg.window_days,
            "feature_columns": ["avg_daily_heuristic"],
            "trained_at": None,
            "mae": None,
            "rmse": None,
            "mape": None,
        }
        prediction_strategy = "heuristica_promedio"

    productos_alta_rotacion, recomendaciones = _compile_high_rotation(
        rotation_df,
        inventory_df,
        cfg,
        demand_predictions,
        prediction_meta,
    )
    tendencias = _calculate_trends(norm_sales, ref_date)

    modelo_demanda = {
        "activo": bool(model_bundle),
        "predicciones_disponibles": bool(demand_predictions),
        "estrategia": prediction_strategy,
        "horizonte_dias": (
            prediction_meta.get("horizon_days") if prediction_meta else None
        ),
        "ventana_dias": prediction_meta.get("window_days") if prediction_meta else None,
        "ultima_actualizacion": (
            prediction_meta.get("trained_at") if prediction_meta else None
        ),
        "mae": prediction_meta.get("mae") if prediction_meta else None,
        "rmse": prediction_meta.get("rmse") if prediction_meta else None,
        "mape": prediction_meta.get("mape") if prediction_meta else None,
        "columnas": prediction_meta.get("feature_columns") if prediction_meta else [],
    }

    metadata = {
        "ventanas_dias": cfg.window_days,
        "horizonte_dias": cfg.horizon_days,
        "ventas_analizadas": int(norm_sales.shape[0]),
        "productos_analizados": int(inventory_df.shape[0]),
        "restocks_disponibles": int(
            0 if restock_rows is None else getattr(restock_rows, "shape", [0])[0]
        ),
        "umbral_alta_rotacion": cfg.high_rotation_threshold,
        "recomendaciones_generadas": len(recomendaciones),
        "modelo_demanda": modelo_demanda,
    }

    report = {
        "fecha_ejecucion": ref_date.date().isoformat(),
        "productos_alta_rotacion": productos_alta_rotacion,
        "recomendaciones_reposicion": recomendaciones,
        "tendencias_predichas": tendencias,
        "metadata": metadata,
    }
    if demand_predictions:
        report["predicciones_demanda"] = demand_predictions
    return report
