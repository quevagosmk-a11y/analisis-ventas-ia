from decimal import Decimal

import pytest

from src import main as app_module
from tests.test_sales_flows import DummyNotifier, FakeConnection, FakeDB


@pytest.fixture()
def registrar_app_client(monkeypatch):
    fake_db = FakeDB()

    def fake_get_conn():
        return FakeConnection(fake_db)

    monkeypatch.setattr(app_module, 'get_db_conn', fake_get_conn)
    monkeypatch.setattr(app_module, 'get_configured_iva_percent', lambda cur: Decimal('19.00'))
    monkeypatch.setattr(app_module, 'load_sales_from_db', lambda *args, **kwargs: None)
    monkeypatch.setattr(app_module, 'Notifier', DummyNotifier)
    monkeypatch.setattr(app_module, 'store_sale_recommendations', lambda *args, **kwargs: None)

    app_module.app.config['TESTING'] = True
    with app_module.app.test_client() as client:
        with client.session_transaction() as sess:
            sess['user_id'] = 42
            sess['role'] = 'admin'
            sess['name'] = 'Tester'
            sess['idle_minutes'] = 45
            sess['session_token'] = 'testing-token'
        yield client, fake_db


def test_registrar_venta(registrar_app_client):
    client, fake_db = registrar_app_client
    payload = {
        'items': [{'id': 1, 'quantity': 1}],
        'payment_method': 'efectivo',
        'force_price': False,
    }

    response = client.post('/api/ventas', json=payload)
    assert response.status_code == 200

    data = response.get_json()
    assert data['success'] is True
    assert data['totals']['subtotal'] == pytest.approx(100.0)
    assert data['totals']['iva'] == pytest.approx(19.0)
    assert data['totals']['total'] == pytest.approx(119.0)
    assert fake_db.ventas, 'Se debe registrar una venta'
    assert fake_db.venta_detalle, 'Se debe registrar el detalle de la venta'
    assert fake_db.products[1]['stock'] == 9
