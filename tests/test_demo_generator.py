import os
import sys
from datetime import date

ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
SRC_DIR = os.path.join(ROOT_DIR, 'src')
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from src.data.demo_generator import (  # noqa: E402
    build_demo_sales_dataframe,
    generate_demo_sales_csv,
)


def test_build_demo_sales_dataframe_returns_consistent_columns():
    df = build_demo_sales_dataframe(
        start_date=date(2025, 1, 1),
        end_date=date(2025, 4, 30),
        seed=2026,
    )
    assert not df.empty
    assert list(df.columns) == ['date', 'product', 'category', 'qty', 'price']
    assert (df['qty'] > 0).all()
    assert (df['price'] > 0).all()
    assert df['product'].nunique() >= 20
    assert df['category'].nunique() >= 5


def test_generate_demo_sales_csv_writes_file(tmp_path):
    out_file = tmp_path / 'demo_sales.csv'
    summary = generate_demo_sales_csv(str(out_file), days=180, seed=99)
    assert out_file.exists()
    assert summary['rows'] > 0
    assert summary['products'] >= 20
    assert summary['categories'] >= 5
    assert summary['date_from'] <= summary['date_to']
