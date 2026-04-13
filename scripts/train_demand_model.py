#!/usr/bin/env python
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd
from joblib import dump
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

try:
    from data.sales_loader import load_sales_data, load_sales_from_db  # noqa: E402
except Exception:
    def load_sales_data(csv_path: str):
        return pd.read_csv(csv_path)

    def load_sales_from_db(*_args, **_kwargs):
        return None

from ai.features import FEATURE_COLUMNS, build_training_dataset  # noqa: E402


def build_db_config() -> Dict[str, str]:
    return {
        "host": os.environ.get("DB_HOST", "localhost"),
        "user": os.environ.get("DB_USER", "root"),
        "password": os.environ.get("DB_PASSWORD", ""),
        "database": os.environ.get("DB_NAME", "la_septima_estrella"),
    }


def load_sales_source(csv_path: Optional[str] = None) -> pd.DataFrame:
    db_config = build_db_config()
    try:
        df = load_sales_from_db(db_config)
    except Exception as exc:
        print(f"[train] No fue posible leer ventas desde MySQL: {exc}")
        df = None
    if df is not None and not df.empty:
        return df

    candidates = []
    if csv_path:
        candidates.append(Path(csv_path))
    candidates.extend([
        ROOT_DIR / "data" / "sales_data.csv",
        ROOT_DIR / "data" / "demo_sales_evaluacion.csv",
        ROOT_DIR / "data" / "sample_sales.csv",
    ])
    for candidate in candidates:
        if candidate.exists():
            print(f"[train] Usando CSV local: {candidate}")
            return load_sales_data(str(candidate))
    raise RuntimeError("No se encontraron datos de ventas en MySQL ni en CSV local.")


def metrics_bundle(y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, float]:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    mae = mean_absolute_error(y_true, y_pred)
    rmse = mean_squared_error(y_true, y_pred) ** 0.5
    with np.errstate(divide="ignore", invalid="ignore"):
        mape = np.mean(np.abs((y_true - y_pred) / np.clip(y_true, 1e-3, None))) * 100.0
    return {
        "mae": float(mae),
        "rmse": float(rmse),
        "mape": float(mape),
    }


def split_train_valid(dataset: pd.DataFrame, train_ratio: float = 0.8) -> Tuple[pd.DataFrame, pd.DataFrame]:
    if dataset.empty:
        return dataset, pd.DataFrame()
    ordered = dataset.sort_values("date").reset_index(drop=True)
    if len(ordered) < 80 or ordered["date"].nunique() < 12:
        return ordered, pd.DataFrame()
    split_idx = max(1, int(len(ordered) * train_ratio))
    split_idx = min(split_idx, len(ordered) - 1)
    train_df = ordered.iloc[:split_idx].copy()
    valid_df = ordered.iloc[split_idx:].copy()
    if train_df.empty or valid_df.empty:
        return ordered, pd.DataFrame()
    return train_df, valid_df


def baseline_predict(features_df: pd.DataFrame, horizon_days: int) -> np.ndarray:
    if "qty_sum_7" in features_df.columns:
        baseline = pd.to_numeric(features_df["qty_sum_7"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
        baseline = baseline / 7.0 * max(horizon_days, 1)
        return np.clip(baseline, a_min=0.0, a_max=None)
    return np.zeros(len(features_df), dtype=float)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Entrena un modelo de demanda basado en ventas históricas."
    )
    parser.add_argument("--window", type=int, default=30, help="Ventana de historial en días para los features.")
    parser.add_argument("--horizon", type=int, default=14, help="Horizonte de predicción en días.")
    parser.add_argument(
        "--output",
        type=str,
        default=str(ROOT_DIR / "models" / "demand_model.joblib"),
        help="Ruta donde se guardará el modelo entrenado.",
    )
    parser.add_argument("--csv", type=str, help="Ruta a un CSV de respaldo si la BD no está disponible.")
    parser.add_argument("--estimators", type=int, default=400, help="Número de árboles del RandomForest.")
    parser.add_argument("--seed", type=int, default=42, help="Semilla aleatoria.")
    args = parser.parse_args()

    try:
        sales_df = load_sales_source(args.csv)
    except Exception as exc:
        print(f"[train] No se pudieron cargar datos de ventas: {exc}")
        return 1

    dataset = build_training_dataset(sales_df, window_days=args.window, horizon_days=args.horizon)
    if dataset.empty:
        print("[train] No hay datos suficientes para entrenar el modelo.")
        return 1

    feature_columns = [col for col in FEATURE_COLUMNS if col in dataset.columns]
    if not feature_columns:
        print("[train] No hay columnas de features disponibles para entrenamiento.")
        return 1

    train_df, valid_df = split_train_valid(dataset)
    eval_model = RandomForestRegressor(
        n_estimators=args.estimators,
        random_state=args.seed,
        n_jobs=-1,
        max_depth=None,
    )
    train_X = train_df[feature_columns].to_numpy(dtype=float)
    train_y = train_df["target"].to_numpy(dtype=float)
    eval_model.fit(train_X, train_y)

    validation_metrics: Dict[str, float] = {}
    baseline_metrics: Dict[str, float] = {}
    if not valid_df.empty:
        valid_X = valid_df[feature_columns].to_numpy(dtype=float)
        valid_y = valid_df["target"].to_numpy(dtype=float)
        valid_pred = np.clip(eval_model.predict(valid_X), a_min=0.0, a_max=None)
        validation_metrics = metrics_bundle(valid_y, valid_pred)

        baseline_pred = baseline_predict(valid_df, args.horizon)
        baseline_metrics = metrics_bundle(valid_y, baseline_pred)

    final_model = RandomForestRegressor(
        n_estimators=args.estimators,
        random_state=args.seed,
        n_jobs=-1,
        max_depth=None,
    )
    full_X = dataset[feature_columns].to_numpy(dtype=float)
    full_y = dataset["target"].to_numpy(dtype=float)
    final_model.fit(full_X, full_y)
    train_pred = np.clip(final_model.predict(full_X), a_min=0.0, a_max=None)
    train_metrics = metrics_bundle(full_y, train_pred)

    metadata = {
        "window_days": args.window,
        "horizon_days": args.horizon,
        "feature_columns": feature_columns,
        "trained_at": datetime.now().astimezone().isoformat(),
        "records": int(len(dataset)),
        "products": int(dataset["product"].nunique()),
        "train_metrics": train_metrics,
        "validation_metrics": validation_metrics or None,
        "baseline_validation_metrics": baseline_metrics or None,
        "split": {
            "train_records": int(len(train_df)),
            "validation_records": int(len(valid_df)),
        },
        "model_type": "RandomForestRegressor",
    }
    if validation_metrics and baseline_metrics:
        metadata["mejora_mape_vs_baseline"] = float(baseline_metrics["mape"] - validation_metrics["mape"])
        metadata["mejora_rmse_vs_baseline"] = float(baseline_metrics["rmse"] - validation_metrics["rmse"])

    artifact = {
        "model": final_model,
        "metadata": metadata,
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    dump(artifact, output_path)

    print(f"[train] Modelo guardado en {output_path}")
    print(
        f"[train] Registros: {metadata['records']} | Productos: {metadata['products']} | "
        f"Train MAPE: {train_metrics['mape']:.2f}%"
    )
    if validation_metrics:
        print(
            f"[train] Validación -> MAE: {validation_metrics['mae']:.2f} | "
            f"RMSE: {validation_metrics['rmse']:.2f} | MAPE: {validation_metrics['mape']:.2f}%"
        )
    if baseline_metrics:
        print(
            f"[train] Baseline validación -> MAE: {baseline_metrics['mae']:.2f} | "
            f"RMSE: {baseline_metrics['rmse']:.2f} | MAPE: {baseline_metrics['mape']:.2f}%"
        )
    if metadata.get("mejora_mape_vs_baseline") is not None:
        print(f"[train] Mejora MAPE vs baseline: {metadata['mejora_mape_vs_baseline']:+.2f} puntos")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
