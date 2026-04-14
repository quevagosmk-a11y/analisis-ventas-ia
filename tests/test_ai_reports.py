import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
SRC_DIR = os.path.join(ROOT_DIR, 'src')
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from datetime import datetime, timezone

import pandas as pd
import pytest

from src import main as app_module
from src.ai import engine as ai_engine


@pytest.fixture()
def admin_session(monkeypatch):
    monkeypatch.setattr(app_module, 'get_session_state', lambda *args, **kwargs: app_module.SessionState(True, False, False, None))
    app_module.app.config['TESTING'] = True
    with app_module.app.test_client() as client:
        with client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['role'] = 'admin'
            sess['name'] = 'Admin'
            sess['session_token'] = 'testing-token'
            sess['idle_minutes'] = 45
            sess['last_activity'] = datetime.now(timezone.utc).isoformat()
        yield client


def test_ai_generate_report_endpoint(monkeypatch, admin_session):
    sample_report = {
        'fecha_ejecucion': '2025-10-20',
        'productos_alta_rotacion': [{'producto': 'Cafe', 'promedio_diario': 1.8, 'compra_sugerida': 6}],
        'recomendaciones_reposicion': [{'producto': 'Cafe', 'compra_sugerida': 6}],
        'tendencias_predichas': [{'producto': 'Arroz', 'variacion_ventas': '+12%'}],
    }
    monkeypatch.setattr(app_module, 'run_ai_report', lambda **kwargs: sample_report)
    response = admin_session.post('/api/ia/reportes', json={})
    assert response.status_code == 200
    data = response.get_json()
    assert data['fecha_ejecucion'] == sample_report['fecha_ejecucion']
    assert 'productos_alta_rotacion' in data
    assert 'recomendaciones_reposicion' in data


def test_ai_last_report_endpoint(monkeypatch, admin_session):
    sample_report = {
        'fecha_ejecucion': '2025-10-21',
        'productos_alta_rotacion': [],
        'recomendaciones_reposicion': [],
        'tendencias_predichas': [],
    }
    monkeypatch.setattr(app_module, 'get_latest_ai_report', lambda: sample_report)
    response = admin_session.get('/api/ia/reportes/ultimo')
    assert response.status_code == 200
    data = response.get_json()
    assert data['fecha_ejecucion'] == sample_report['fecha_ejecucion']


def test_ai_report_requires_admin(monkeypatch):
    monkeypatch.setattr(app_module, 'get_session_state', lambda *args, **kwargs: app_module.SessionState(True, False, False, None))
    app_module.app.config['TESTING'] = True
    with app_module.app.test_client() as client:
        with client.session_transaction() as sess:
            sess['user_id'] = 2
            sess['role'] = 'vendedor'
            sess['session_token'] = 'testing-token'
            sess['idle_minutes'] = 45
            sess['last_activity'] = datetime.now(timezone.utc).isoformat()
        resp = client.post('/api/ia/reportes', json={})
        assert resp.status_code == 403


def _sample_sales_df():
    return pd.DataFrame(
        {
            'product': ['Cafe', 'Cafe', 'Pan'],
            'qty': [3, 2, 4],
            'price': [3000.0, 3000.0, 1800.0],
            'total': [9000.0, 6000.0, 7200.0],
            'date': pd.to_datetime(['2025-10-01', '2025-10-02', '2025-10-02']),
            'timestamp': pd.to_datetime(['2025-10-01', '2025-10-02', '2025-10-02']),
        }
    )


def test_ia_forecast_endpoint_returns_payload(monkeypatch, admin_session):
    monkeypatch.setattr(app_module, 'load_sales_dataframe_for_ai', lambda *args, **kwargs: _sample_sales_df())
    monkeypatch.setattr(
        app_module,
        'fetch_inventory_snapshot',
        lambda: [
            {'id': 1, 'nombre': 'Cafe', 'categoria': 'Bebidas', 'stock': 3, 'min_stock': 2},
            {'id': 2, 'nombre': 'Pan', 'categoria': 'Panaderia', 'stock': 12, 'min_stock': 3},
        ],
    )
    monkeypatch.setattr(
        app_module,
        'generate_ai_report',
        lambda *args, **kwargs: {
            'recomendaciones_reposicion': [{'producto': 'Cafe', 'compra_sugerida': 8}],
            'predicciones_demanda': {
                'Cafe': {'predicted_demand': 10.0, 'feature_date': '2025-10-02'},
                'Pan': {'predicted_demand': 5.0, 'feature_date': '2025-10-02'},
            },
            'metadata': {
                'modelo_demanda': {
                    'activo': True,
                    'predicciones_disponibles': True,
                    'estrategia': 'modelo_entrenado',
                    'horizonte_dias': 14,
                    'ventana_dias': 30,
                    'ultima_actualizacion': '2025-10-03T08:00:00-05:00',
                    'mae': 1.2,
                    'rmse': 1.7,
                    'mape': 18.5,
                }
            },
        },
    )
    response = admin_session.get('/api/ia/pronostico-demanda?from=2025-10-01&to=2025-10-31&horizon=14&limit=10')
    assert response.status_code == 200
    data = response.get_json()
    assert data['success'] is True
    assert data['model']['strategy'] == 'modelo_entrenado'
    assert data['model']['quality'] == 'alta'
    assert data['summary']['products'] == 2
    assert data['forecast'][0]['risk_level'] in {'critico', 'alerta', 'estable', 'sin_dato'}
    assert any(item['product'] == 'Cafe' for item in data['forecast'])
    assert 'predicted_qty' in data['forecast'][0]
    assert 'predicted_daily' in data['forecast'][0]


def test_ia_forecast_endpoint_validates_inputs(admin_session):
    response = admin_session.get('/api/ia/pronostico-demanda?horizon=200')
    assert response.status_code == 400
    payload = response.get_json()
    assert payload['success'] is False
    assert 'horizon' in (payload.get('error') or '')


def test_ia_forecast_endpoint_without_sales(admin_session, monkeypatch):
    monkeypatch.setattr(app_module, 'load_sales_dataframe_for_ai', lambda *args, **kwargs: pd.DataFrame())
    monkeypatch.setattr(
        app_module,
        'fetch_inventory_snapshot',
        lambda: [
            {'id': 1, 'nombre': 'Cafe', 'categoria': 'Bebidas', 'stock': 1, 'min_stock': 4},
            {'id': 2, 'nombre': 'Pan', 'categoria': 'Panaderia', 'stock': 8, 'min_stock': 3},
        ],
    )
    response = admin_session.get('/api/ia/pronostico-demanda')
    assert response.status_code == 200
    payload = response.get_json()
    assert payload['success'] is True
    assert payload['period']['inventory_only'] is True
    assert payload['summary']['products'] >= 1


def test_ia_forecast_includes_product_image_urls(admin_session, monkeypatch):
    monkeypatch.setattr(
        app_module,
        'load_sales_dataframe_for_ai',
        lambda *args, **kwargs: _sample_sales_df(),
    )
    monkeypatch.setattr(
        app_module,
        'fetch_inventory_snapshot',
        lambda: [
            {
                'id': 1,
                'nombre': 'Cafe',
                'categoria': 'Bebidas',
                'stock': 3,
                'min_stock': 2,
                'imagen_b64': 'aGVsbG8=',
                'imagen_mime': 'image/png',
            }
        ],
    )
    monkeypatch.setattr(
        app_module,
        'generate_ai_report',
        lambda *args, **kwargs: {
            'predicciones_demanda': {
                'Cafe': {'predicted_demand': 10.0, 'feature_date': '2025-10-02'},
            },
            'metadata': {'modelo_demanda': {'estrategia': 'modelo_entrenado', 'mape': 18.5}},
        },
    )
    response = admin_session.get('/api/ia/pronostico-demanda?from=2025-10-01&to=2025-10-31&horizon=14&limit=10')
    assert response.status_code == 200
    payload = response.get_json()
    assert payload['success'] is True
    assert payload['forecast'][0]['image_url'] == 'data:image/png;base64,aGVsbG8='


def test_generate_ai_report_heuristic_uses_calendar_window(monkeypatch):
    monkeypatch.setattr(ai_engine, 'get_demand_model_bundle', lambda: None)
    sales_df = pd.DataFrame(
        {
            'product': ['Cafe', 'Cafe'],
            'qty': [10, 10],
            'price': [3000.0, 3000.0],
            'total': [30000.0, 30000.0],
            'date': pd.to_datetime(['2025-01-01', '2025-01-02']),
            'timestamp': pd.to_datetime(['2025-01-01', '2025-01-02']),
        }
    )

    report = ai_engine.generate_ai_report(
        sales_df,
        [{'nombre': 'Cafe', 'stock': 3, 'min_stock': 2, 'categoria': 'Bebidas'}],
        today=datetime(2025, 1, 30),
        config=ai_engine.AIEngineConfig(window_days=30, horizon_days=14),
    )

    predicted = report['predicciones_demanda']['Cafe']['predicted_demand']
    assert predicted == pytest.approx(9.33, abs=0.01)


def test_generate_ai_report_heuristic_backfills_products_outside_recent_window(monkeypatch):
    monkeypatch.setattr(ai_engine, 'get_demand_model_bundle', lambda: None)
    sales_df = pd.DataFrame(
        {
            'product': ['Cafe', 'Cafe', 'Arroz'],
            'qty': [10, 10, 12],
            'price': [3000.0, 3000.0, 4500.0],
            'total': [30000.0, 30000.0, 54000.0],
            'date': pd.to_datetime(['2025-01-28', '2025-01-29', '2024-12-01']),
            'timestamp': pd.to_datetime(['2025-01-28', '2025-01-29', '2024-12-01']),
        }
    )

    report = ai_engine.generate_ai_report(
        sales_df,
        [
            {'nombre': 'Cafe', 'stock': 3, 'min_stock': 2, 'categoria': 'Bebidas'},
            {'nombre': 'Arroz', 'stock': 2, 'min_stock': 4, 'categoria': 'Despensa'},
        ],
        today=datetime(2025, 1, 30),
        config=ai_engine.AIEngineConfig(window_days=30, horizon_days=14),
    )

    assert report['metadata']['modelo_demanda']['estrategia'] == 'heuristica_promedio'
    assert report['predicciones_demanda']['Cafe']['predicted_demand'] == pytest.approx(9.33, abs=0.01)
    assert report['predicciones_demanda']['Arroz']['predicted_demand'] > 0


def test_build_demand_forecast_rows_uses_current_date_for_runout(monkeypatch):
    monkeypatch.setattr(
        app_module,
        'bogota_now_naive',
        lambda: datetime(2025, 1, 20),
    )

    rows = app_module.build_demand_forecast_rows(
        inventory_rows=[
            {'nombre': 'Cafe', 'categoria': 'Bebidas', 'stock': 10, 'min_stock': 2}
        ],
        report={
            'predicciones_demanda': {
                'Cafe': {'predicted_demand': 14.0}
            }
        },
        horizon_days=14,
        latest_reference=datetime(2025, 1, 2),
        limit=10,
    )

    assert rows[0]['runout_date'] == '2025-01-30'
