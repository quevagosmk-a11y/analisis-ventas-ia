from __future__ import annotations

from typing import Dict, List

import numpy as np
import pandas as pd

FEATURE_COLUMNS: List[str] = [
    "qty_sum_7",
    "qty_sum_30",
    "avg_price_7",
    "avg_price_30",
    "std_qty_7",
    "days_since_sale",
    "day_of_week",
    "month",
    "trend_7_vs_14",
    "qty_mean_7",
]


def _prepare_daily_sales(sales_df: pd.DataFrame) -> pd.DataFrame:
    df = sales_df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])
    df["product"] = df["product"].fillna("Producto sin nombre")
    df["qty"] = pd.to_numeric(df["qty"], errors="coerce").fillna(0.0)
    df["price"] = pd.to_numeric(df.get("price"), errors="coerce").fillna(0.0)
    grouped = (
        df.groupby(["product", "date"], as_index=False)
        .agg(qty=("qty", "sum"), price=("price", "mean"))
        .sort_values(["product", "date"])
    )
    return grouped


def _compute_features_for_group(
    group: pd.DataFrame, window_days: int, horizon_days: int
) -> pd.DataFrame:
    grp = group.sort_values("date").copy()
    qty = grp["qty"]
    price = grp["price"]

    grp["qty_sum_7"] = qty.rolling(window=7, min_periods=1).sum().shift(1).fillna(0.0)
    grp["qty_sum_30"] = (
        qty.rolling(window=window_days, min_periods=1).sum().shift(1).fillna(0.0)
    )
    grp["avg_price_7"] = (
        price.rolling(window=7, min_periods=1).mean().shift(1).bfill().fillna(0.0)
    )
    grp["avg_price_30"] = (
        price.rolling(window=window_days, min_periods=1)
        .mean()
        .shift(1)
        .bfill()
        .fillna(0.0)
    )
    grp["std_qty_7"] = qty.rolling(window=7, min_periods=1).std().shift(1).fillna(0.0)
    grp["qty_mean_7"] = qty.rolling(window=7, min_periods=1).mean().shift(1).fillna(0.0)

    diff_days = (
        grp["date"]
        .diff()
        .dt.days.fillna(window_days)
        .clip(lower=0, upper=window_days * 2)
    )
    grp["days_since_sale"] = diff_days

    grp["day_of_week"] = grp["date"].dt.dayofweek
    grp["month"] = grp["date"].dt.month

    prev_7 = qty.shift(1).rolling(window=7, min_periods=1).sum()
    prev_14 = qty.shift(1).rolling(window=14, min_periods=1).sum()
    trend_den = (prev_14 - prev_7).replace(0, np.nan)
    grp["trend_7_vs_14"] = (
        (prev_7 / trend_den).replace([np.inf, -np.inf], np.nan).fillna(1.0)
    )

    future_sum = (
        qty.shift(-1).rolling(window=horizon_days, min_periods=horizon_days).sum()
    )
    grp["target"] = future_sum

    return grp


def build_training_dataset(
    sales_df: pd.DataFrame,
    *,
    window_days: int = 30,
    horizon_days: int = 14,
) -> pd.DataFrame:
    daily = _prepare_daily_sales(sales_df)
    if daily.empty:
        return pd.DataFrame(columns=["product", "date", *FEATURE_COLUMNS, "target"])

    records: List[pd.DataFrame] = []
    for product, group in daily.groupby("product"):
        enriched = _compute_features_for_group(
            group, window_days=window_days, horizon_days=horizon_days
        )
        enriched["product"] = product
        records.append(enriched)

    dataset = pd.concat(records, ignore_index=True)
    dataset = dataset.dropna(subset=["target"])
    dataset[FEATURE_COLUMNS] = dataset[FEATURE_COLUMNS].fillna(0.0)
    dataset["target"] = dataset["target"].clip(lower=0.0)
    return dataset[["product", "date", *FEATURE_COLUMNS, "target"]]


def build_latest_features(
    sales_df: pd.DataFrame,
    *,
    window_days: int = 30,
    horizon_days: int = 14,
) -> pd.DataFrame:
    daily = _prepare_daily_sales(sales_df)
    if daily.empty:
        return pd.DataFrame(columns=["product", "feature_date", *FEATURE_COLUMNS])

    rows: List[Dict[str, float]] = []
    for product, group in daily.groupby("product"):
        enriched = _compute_features_for_group(
            group, window_days=window_days, horizon_days=horizon_days
        )
        latest = enriched.tail(1)
        if latest.empty:
            continue
        item: Dict[str, float] = {
            "product": product,
            "feature_date": latest["date"].iloc[0],
        }
        for column in FEATURE_COLUMNS:
            item[column] = float(latest[column].iloc[0]) if column in latest else 0.0
        rows.append(item)

    return pd.DataFrame(rows)
