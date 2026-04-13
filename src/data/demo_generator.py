from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class ProductProfile:
    name: str
    category: str
    base_price: float
    base_daily_demand: float
    weekend_multiplier: float = 1.0
    promo_probability: float = 0.08
    trend_end: float = 0.0
    price_sigma: float = 0.035


PRODUCT_PROFILES: List[ProductProfile] = [
    ProductProfile(
        "Gaseosa Cola 400ml",
        "Bebidas",
        3050,
        4.2,
        weekend_multiplier=1.28,
        promo_probability=0.10,
        trend_end=0.07,
    ),
    ProductProfile(
        "Gaseosa Manzana 400ml",
        "Bebidas",
        2480,
        3.6,
        weekend_multiplier=1.26,
        promo_probability=0.10,
        trend_end=0.07,
    ),
    ProductProfile(
        "Agua 600ml",
        "Bebidas",
        2400,
        3.8,
        weekend_multiplier=1.14,
        promo_probability=0.06,
        trend_end=0.04,
    ),
    ProductProfile(
        "Jugo Mango 300ml",
        "Bebidas",
        1492,
        2.6,
        weekend_multiplier=1.18,
        promo_probability=0.09,
        trend_end=0.08,
    ),
    ProductProfile(
        "Bebida Energetica 250ml",
        "Bebidas",
        1820,
        1.8,
        weekend_multiplier=1.20,
        promo_probability=0.10,
        trend_end=0.10,
    ),
    ProductProfile(
        "Cerveza Sixpack",
        "Bebidas",
        21000,
        1.2,
        weekend_multiplier=1.38,
        promo_probability=0.08,
        trend_end=0.05,
    ),
    ProductProfile(
        "Papas 30g",
        "Snacks",
        2500,
        4.5,
        weekend_multiplier=1.30,
        promo_probability=0.11,
        trend_end=0.09,
    ),
    ProductProfile(
        "Mani 50g",
        "Snacks",
        2240,
        2.1,
        weekend_multiplier=1.22,
        promo_probability=0.09,
        trend_end=0.07,
    ),
    ProductProfile(
        "Galletas Chocolate",
        "Snacks",
        6850,
        2.3,
        weekend_multiplier=1.18,
        promo_probability=0.08,
        trend_end=0.07,
    ),
    ProductProfile(
        "Chitos 40g",
        "Snacks",
        1800,
        2.4,
        weekend_multiplier=1.20,
        promo_probability=0.09,
        trend_end=0.07,
    ),
    ProductProfile(
        "Leche Entera 900ml",
        "Lacteos",
        2950,
        3.5,
        weekend_multiplier=1.04,
        promo_probability=0.06,
        trend_end=0.03,
    ),
    ProductProfile(
        "Yogurt Fresa 200ml",
        "Lacteos",
        3150,
        2.9,
        weekend_multiplier=1.07,
        promo_probability=0.08,
        trend_end=0.05,
    ),
    ProductProfile(
        "Queso Campesino 250g",
        "Lacteos",
        7040,
        1.6,
        weekend_multiplier=1.08,
        promo_probability=0.07,
        trend_end=0.04,
    ),
    ProductProfile(
        "Arroz 1kg",
        "Despensa",
        3656,
        1.9,
        weekend_multiplier=0.95,
        promo_probability=0.05,
        trend_end=0.02,
    ),
    ProductProfile(
        "Aceite 1L",
        "Despensa",
        7100,
        1.2,
        weekend_multiplier=0.92,
        promo_probability=0.05,
        trend_end=0.01,
    ),
    ProductProfile(
        "Azucar 1kg",
        "Despensa",
        5110,
        1.5,
        weekend_multiplier=0.95,
        promo_probability=0.05,
        trend_end=0.02,
    ),
    ProductProfile(
        "Huevos x30",
        "Despensa",
        15960,
        1.3,
        weekend_multiplier=1.00,
        promo_probability=0.04,
        trend_end=0.02,
    ),
    ProductProfile(
        "Harina Trigo 1kg",
        "Despensa",
        4690,
        1.3,
        weekend_multiplier=0.96,
        promo_probability=0.05,
        trend_end=0.02,
    ),
    ProductProfile(
        "Sal 500g",
        "Despensa",
        1580,
        1.0,
        weekend_multiplier=0.95,
        promo_probability=0.04,
        trend_end=0.01,
    ),
    ProductProfile(
        "Frijol 500g",
        "Granos",
        7040,
        1.1,
        weekend_multiplier=0.94,
        promo_probability=0.05,
        trend_end=0.02,
    ),
    ProductProfile(
        "Lenteja 500g",
        "Granos",
        2550,
        1.1,
        weekend_multiplier=0.94,
        promo_probability=0.05,
        trend_end=0.02,
    ),
    ProductProfile(
        "Jabon Barra",
        "Aseo",
        2820,
        1.4,
        weekend_multiplier=0.93,
        promo_probability=0.06,
        trend_end=0.03,
    ),
    ProductProfile(
        "Detergente 500g",
        "Aseo",
        5310,
        1.0,
        weekend_multiplier=0.90,
        promo_probability=0.06,
        trend_end=0.03,
    ),
    ProductProfile(
        "Papel Higienico x4",
        "Aseo",
        14580,
        0.8,
        weekend_multiplier=0.91,
        promo_probability=0.05,
        trend_end=0.03,
    ),
    ProductProfile(
        "Pan Tajado 500g",
        "Panaderia",
        6450,
        1.9,
        weekend_multiplier=1.16,
        promo_probability=0.08,
        trend_end=0.04,
    ),
    ProductProfile(
        "Pan Blandito x5",
        "Panaderia",
        12500,
        1.6,
        weekend_multiplier=1.18,
        promo_probability=0.08,
        trend_end=0.04,
    ),
    ProductProfile(
        "Cafe Molido 250g",
        "Despensa",
        15300,
        1.0,
        weekend_multiplier=0.98,
        promo_probability=0.06,
        trend_end=0.04,
    ),
    ProductProfile(
        "Chocolate 250g",
        "Despensa",
        16050,
        0.9,
        weekend_multiplier=0.98,
        promo_probability=0.06,
        trend_end=0.04,
    ),
]


def _category_month_multiplier(category: str, month: int) -> float:
    if category == "Bebidas":
        if month in {12, 1, 2}:
            return 1.20
        if month in {6, 7, 8}:
            return 1.10
        return 1.0
    if category == "Snacks":
        if month in {6, 7, 12}:
            return 1.14
        return 1.0
    if category == "Lacteos":
        return 1.03 if month in {1, 2, 3, 11, 12} else 1.0
    if category == "Panaderia":
        return 1.08 if month in {12, 1} else 1.0
    if category == "Despensa":
        return 1.05 if month in {1, 6, 12} else 1.0
    return 1.0


def _payday_multiplier(day_of_month: int) -> float:
    if day_of_month in {14, 15, 29, 30}:
        return 1.10
    if day_of_month in {1, 2}:
        return 1.06
    return 1.0


def _ensure_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return datetime.strptime(value, "%Y-%m-%d").date()
    raise ValueError("Fecha invalida para generar datos demo.")


def build_demo_sales_dataframe(
    *,
    start_date: Any,
    end_date: Any,
    seed: int = 2026,
) -> pd.DataFrame:
    start = _ensure_date(start_date)
    end = _ensure_date(end_date)
    if end < start:
        raise ValueError("end_date no puede ser menor que start_date.")

    days_span = (end - start).days + 1
    dates = [start + timedelta(days=offset) for offset in range(days_span)]
    rng = np.random.default_rng(seed)
    rows: List[Dict[str, Any]] = []

    for profile in PRODUCT_PROFILES:
        trend_series = np.linspace(1.0, 1.0 + profile.trend_end, len(dates))
        promo_roll = rng.random(len(dates))
        for idx, current_date in enumerate(dates):
            dow = current_date.weekday()
            weekend_factor = profile.weekend_multiplier if dow >= 4 else 1.0
            seasonal_factor = _category_month_multiplier(
                profile.category, current_date.month
            )
            payroll_factor = _payday_multiplier(current_date.day)

            demand_mean = (
                profile.base_daily_demand
                * trend_series[idx]
                * weekend_factor
                * seasonal_factor
                * payroll_factor
            )
            demand_mean = max(demand_mean, 0.15)
            qty = int(rng.poisson(lam=demand_mean))

            is_promo = promo_roll[idx] < profile.promo_probability
            promo_discount = 0.0
            if is_promo:
                promo_discount = float(rng.uniform(0.06, 0.18))
                promo_boost = float(rng.uniform(1.20, 1.85))
                qty = int(round(max(qty, 1) * promo_boost))

            if qty <= 0:
                continue

            price_noise = float(rng.normal(0.0, profile.price_sigma))
            price = profile.base_price * (1.0 + price_noise)
            if is_promo:
                price *= 1.0 - promo_discount
            price = float(max(700, int(round(max(700.0, price) / 50.0) * 50)))

            rows.append(
                {
                    "date": current_date.isoformat(),
                    "product": profile.name,
                    "category": profile.category,
                    "qty": int(qty),
                    "price": float(price),
                }
            )

    if not rows:
        raise ValueError("No se pudieron generar filas de ventas demo.")

    df = pd.DataFrame(rows, columns=["date", "product", "category", "qty", "price"])
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = (
        df.dropna(subset=["date"])
        .sort_values(["date", "product"])
        .reset_index(drop=True)
    )
    df["date"] = df["date"].dt.strftime("%Y-%m-%d")
    return df


def generate_demo_sales_csv(
    output_path: str,
    *,
    days: int = 420,
    seed: int = 2026,
    end_date: Optional[Any] = None,
) -> Dict[str, Any]:
    if days < 90:
        raise ValueError("days debe ser al menos 90 para un escenario realista.")
    if end_date is None:
        end = date.today() - timedelta(days=1)
    else:
        end = _ensure_date(end_date)
    start = end - timedelta(days=days - 1)
    df = build_demo_sales_dataframe(start_date=start, end_date=end, seed=seed)

    output = Path(output_path).expanduser()
    if not output.is_absolute():
        output = (Path.cwd() / output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output, index=False, encoding="utf-8")

    summary = {
        "path": str(output),
        "rows": int(len(df)),
        "products": int(df["product"].nunique()),
        "categories": int(df["category"].nunique()),
        "date_from": str(df["date"].min()),
        "date_to": str(df["date"].max()),
        "seed": int(seed),
        "days": int(days),
    }
    return summary
