import os
import sys

import pandas as pd

ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
SRC_DIR = os.path.join(ROOT_DIR, 'src')
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from src import main as app_module


def sample_sales_df():
    return pd.DataFrame({
        'product': ['Leche entera', 'Pan integral'],
        'category': ['Lacteos', 'Panaderia'],
        'qty': [10, 5],
        'price': [4500.0, 3200.0],
        'total': [45000.0, 16000.0],
        'timestamp': pd.to_datetime(['2025-01-10', '2025-01-09']),
        'payment_method': ['efectivo', 'tarjeta'],
    })


def test_generate_chat_response_stock_question(monkeypatch):
    monkeypatch.setattr(
        app_module,
        'fetch_inventory_snapshot',
        lambda: [
            {'id': 1, 'nombre': 'Leche entera', 'precio': 4500.0, 'stock': 5, 'min_stock': 2},
            {'id': 2, 'nombre': 'Pan integral', 'precio': 3200.0, 'stock': 9, 'min_stock': 3},
        ]
    )
    answer, _ = app_module.generate_chat_response('Cuanta leche queda en inventario?', sample_sales_df())
    assert 'Leche entera' in answer
    assert '5 unidades' in answer or '5 unidades' in answer.replace('unidad', 'unidades')


def test_generate_chat_response_combo_question(monkeypatch):
    monkeypatch.setattr(
        app_module,
        'fetch_inventory_snapshot',
        lambda: [
            {'id': 1, 'nombre': 'Leche entera', 'precio': 4500.0, 'stock': 5, 'min_stock': 2},
            {'id': 2, 'nombre': 'Pan integral', 'precio': None, 'stock': 9, 'min_stock': 3},
        ]
    )
    answer, _ = app_module.generate_chat_response('Hazme un combo con leche entera y pan integral y dime el precio', sample_sales_df())
    assert 'Precio aproximado' in answer
    assert 'Leche entera' in answer and 'Pan integral' in answer


def test_generate_chat_response_greeting_returns_help(monkeypatch):
    monkeypatch.setattr(app_module, 'fetch_inventory_snapshot', lambda: [])
    answer, _ = app_module.generate_chat_response('hola', sample_sales_df())
    assert 'Puedo ayudarte con ventas' in answer
    assert 'Acumulado analizado' not in answer


def test_build_product_catalog_snapshot_uses_main_inventory_fetcher(monkeypatch):
    monkeypatch.setattr(
        app_module,
        'fetch_inventory_snapshot',
        lambda: [
            {'id': 7, 'nombre': 'Cafe molido', 'precio': 12500.0, 'stock': 4, 'min_stock': 2},
        ],
    )

    catalog = app_module.build_product_catalog_snapshot()

    assert catalog == [
        {
            'id': 7,
            'name': 'Cafe molido',
            'norm': 'cafe molido',
            'price': 12500.0,
            'stock': 4,
            'min_stock': 2,
        }
    ]


def test_compute_chat_insights_uses_main_inventory_fetcher(monkeypatch):
    monkeypatch.setattr(
        app_module,
        'fetch_inventory_snapshot',
        lambda: [
            {'id': 3, 'nombre': 'Huevos AA', 'precio': 18000.0, 'stock': 6, 'min_stock': 4},
        ],
    )

    insights = app_module.compute_chat_insights(sample_sales_df())

    assert insights['inventory_snapshot'] is True
