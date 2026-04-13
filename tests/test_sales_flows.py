import os
import sys
from decimal import Decimal

ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
SRC_DIR = os.path.join(ROOT_DIR, 'src')
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

import pytest

from src import main as app_module


class FakeDB:
    def __init__(self):
        self.products = {
            1: {
                'id': 1,
                'nombre': 'Cafe Premium',
                'precio': '100.00',
                'stock': 10,
                'iva_percent': '19.00',
            }
        }
        self.users = {
            42: {'id': 42, 'username': 'tester42', 'name': 'Tester 42'},
            99: {'id': 99, 'username': 'tester99', 'name': 'Tester 99'},
        }
        self.ventas = []
        self.venta_detalle = []
        self.price_audit = []
        self.inventory_movements = []
        self.audit_events = []
        self.next_sale_id = 1
        self.next_movement_id = 1
        self.fail_on = None


class FakeConnection:
    def __init__(self, db):
        self.db = db
        self._undo_stack = []
        self._in_transaction = False

    def cursor(self, dictionary=False):
        return FakeCursor(self, dictionary=dictionary)

    def start_transaction(self):
        self._in_transaction = True
        self._undo_stack = []

    def register_undo(self, action):
        if self._in_transaction:
            self._undo_stack.append(action)

    def commit(self):
        self._undo_stack = []
        self._in_transaction = False

    def rollback(self):
        while self._undo_stack:
            undo = self._undo_stack.pop()
            undo()
        self._in_transaction = False

    def close(self):
        pass


class FakeCursor:
    def __init__(self, connection, dictionary=False):
        self.connection = connection
        self.db = connection.db
        self.dictionary = dictionary
        self._results = []
        self.lastrowid = None
        self.rowcount = 0

    def execute(self, query, params=None):
        normalized = ' '.join(query.strip().lower().split())
        self.rowcount = 0
        if normalized.startswith('show tables like'):
            self._results = [('fake_table',)]
            return
        if normalized.startswith('show columns from'):
            # En pruebas asumimos esquema completo para evitar migraciones reales.
            self._results = [('fake_col',)]
            return
        if normalized.startswith('show index from'):
            self._results = [('fake_idx',)]
            return
        if normalized.startswith('alter table'):
            self._results = []
            return
        if normalized.startswith('create table'):
            self._results = []
            return
        if normalized.startswith('insert into ventas'):
            sale_id = self.db.next_sale_id
            self.db.next_sale_id += 1
            record = {
                'id': sale_id,
                'fecha': '2026-03-19T12:00:00',
                'usuario_id': params[0],
                'metodo_pago': params[1],
                'total': 0.0,
                'iva_percent': 0.0,
            }
            self.db.ventas.append(record)
            self.lastrowid = sale_id
            self.rowcount = 1
            self.connection.register_undo(lambda: self.db.ventas.pop())
            self._results = []
            return
        if normalized.startswith('select nombre, precio, stock, iva_percent from productos where id'):
            product_id = params[0]
            product = self.db.products.get(product_id)
            if product:
                if self.dictionary:
                    self._results = [product.copy()]
                else:
                    self._results = [(
                        product['nombre'],
                        product['precio'],
                        product['stock'],
                        product.get('iva_percent'),
                    )]
            else:
                self._results = []
            return
        if normalized.startswith('select nombre, precio, stock from productos where id'):
            product_id = params[0]
            product = self.db.products.get(product_id)
            if product:
                if self.dictionary:
                    self._results = [product.copy()]
                else:
                    self._results = [(product['nombre'], product['precio'], product['stock'])]
            else:
                self._results = []
            return
        if normalized.startswith('select id, nombre, stock from productos where id'):
            product_id = params[0]
            product = self.db.products.get(product_id)
            if product:
                row = {'id': product['id'], 'nombre': product['nombre'], 'stock': product['stock']}
                self._results = [row] if self.dictionary else [(row['id'], row['nombre'], row['stock'])]
            else:
                self._results = []
            return
        if normalized.startswith('insert into venta_detalle'):
            if self.db.fail_on == 'venta_detalle':
                self.db.fail_on = None
                raise RuntimeError('simulated failure during sale detail insert')
            if len(params) == 5:
                venta_id, product_id, quantity, price, iva_percent = params
            else:
                venta_id, product_id, quantity, price = params
                iva_percent = 0.0
            detail = {
                'venta_id': venta_id,
                'producto_id': product_id,
                'cantidad': quantity,
                'precio': price,
                'iva_percent': iva_percent,
            }
            self.db.venta_detalle.append(detail)
            self.rowcount = 1
            self.connection.register_undo(lambda: self.db.venta_detalle.pop())
            self._results = []
            return
        if normalized.startswith('update productos set stock = stock -'):
            quantity, product_id = params
            product = self.db.products[product_id]
            previous = product['stock']
            product['stock'] = previous - quantity
            self.rowcount = 1
            self.connection.register_undo(lambda prod=product, prev=previous: prod.__setitem__('stock', prev))
            self._results = []
            return
        if normalized.startswith('update productos set stock='):
            stock, product_id = params
            product = self.db.products[product_id]
            previous = product['stock']
            product['stock'] = int(stock)
            self.rowcount = 1
            self.connection.register_undo(lambda prod=product, prev=previous: prod.__setitem__('stock', prev))
            self._results = []
            return
        if normalized.startswith('update ventas set total'):
            if len(params) == 3:
                total, iva_percent, venta_id = params
            else:
                total, venta_id = params
                iva_percent = None
            for record in self.db.ventas:
                if record['id'] == venta_id:
                    previous = record['total']
                    previous_iva = record.get('iva_percent', 0.0)
                    record['total'] = total
                    if iva_percent is not None:
                        record['iva_percent'] = iva_percent
                    self.rowcount = 1
                    self.connection.register_undo(
                        lambda rec=record, prev=previous, prev_iva=previous_iva: rec.update({'total': prev, 'iva_percent': prev_iva})
                    )
                    break
            self._results = []
            return
        if normalized.startswith('select v.id, v.fecha, v.total, v.metodo_pago, v.iva_percent'):
            venta_id = params[0]
            venta = next((row for row in self.db.ventas if row['id'] == venta_id), None)
            if not venta:
                self._results = []
                return
            user = self.db.users.get(
                venta['usuario_id'],
                {
                    'id': venta['usuario_id'],
                    'username': f"user_{venta['usuario_id']}",
                    'name': f"User {venta['usuario_id']}",
                },
            )
            row = {
                'id': venta['id'],
                'fecha': venta['fecha'],
                'total': venta['total'],
                'metodo_pago': venta['metodo_pago'],
                'iva_percent': venta.get('iva_percent', 0.0),
                'usuario_id': user['id'],
                'username': user['username'],
                'name': user['name'],
            }
            self._results = [row] if self.dictionary else [tuple(row.values())]
            return
        if normalized.startswith('select vd.producto_id, p.nombre, vd.cantidad, vd.precio, vd.iva_percent'):
            venta_id = params[0]
            rows = []
            for detail in self.db.venta_detalle:
                if detail['venta_id'] != venta_id:
                    continue
                product = self.db.products.get(detail['producto_id'], {})
                row = {
                    'producto_id': detail['producto_id'],
                    'nombre': product.get('nombre'),
                    'cantidad': detail['cantidad'],
                    'precio': detail['precio'],
                    'iva_percent': detail.get('iva_percent', 0.0),
                }
                rows.append(row)
            self._results = rows if self.dictionary else [tuple(row.values()) for row in rows]
            return
        if normalized.startswith('select combos, restock, estado from venta_recomendaciones'):
            self._results = []
            return
        if normalized.startswith('insert into producto_precio_auditoria'):
            producto_id, usuario_id, precio_anterior, precio_nuevo, motivo = params
            entry = {
                'producto_id': producto_id,
                'usuario_id': usuario_id,
                'precio_anterior': precio_anterior,
                'precio_nuevo': precio_nuevo,
                'motivo': motivo,
            }
            self.db.price_audit.append(entry)
            self.rowcount = 1
            self.connection.register_undo(lambda: self.db.price_audit.pop())
            self._results = []
            return
        if normalized.startswith('insert into inventario_movimientos'):
            movimiento_id = self.db.next_movement_id
            self.db.next_movement_id += 1
            producto_id, tipo, cantidad, stock_anterior, stock_nuevo, motivo, usuario_id = params
            entry = {
                'id': movimiento_id,
                'producto_id': producto_id,
                'tipo': tipo,
                'cantidad': cantidad,
                'stock_anterior': stock_anterior,
                'stock_nuevo': stock_nuevo,
                'motivo': motivo,
                'usuario_id': usuario_id,
            }
            self.db.inventory_movements.append(entry)
            self.lastrowid = movimiento_id
            self.rowcount = 1
            self.connection.register_undo(lambda: self.db.inventory_movements.pop())
            self._results = []
            return
        if normalized.startswith('insert into auditoria_eventos'):
            event_type, entity_type, entity_id, description, details_json, actor_user_id, actor_username = params
            entry = {
                'event_type': event_type,
                'entity_type': entity_type,
                'entity_id': entity_id,
                'description': description,
                'details_json': details_json,
                'actor_user_id': actor_user_id,
                'actor_username': actor_username,
            }
            self.db.audit_events.append(entry)
            self.rowcount = 1
            self.connection.register_undo(lambda: self.db.audit_events.pop())
            self._results = []
            return
        if 'from inventario_movimientos m' in normalized:
            rows = list(self.db.inventory_movements)
            rows.sort(key=lambda item: item['id'], reverse=True)
            limit = params[-1] if params else len(rows)
            try:
                limit = int(limit)
            except (TypeError, ValueError):
                limit = len(rows)
            rows = rows[:max(0, limit)]
            if self.dictionary:
                self._results = [
                    {
                        'id': row['id'],
                        'producto_id': row['producto_id'],
                        'producto_nombre': self.db.products.get(row['producto_id'], {}).get('nombre'),
                        'tipo': row['tipo'],
                        'cantidad': row['cantidad'],
                        'stock_anterior': row['stock_anterior'],
                        'stock_nuevo': row['stock_nuevo'],
                        'motivo': row['motivo'],
                        'usuario_id': row['usuario_id'],
                        'usuario': f"user_{row['usuario_id']}" if row.get('usuario_id') else None,
                        'creado_en': '2026-02-16 12:00:00',
                    }
                    for row in rows
                ]
            else:
                self._results = []
            return
        raise NotImplementedError(query)

    def fetchone(self):
        if not self._results:
            return None
        value = self._results.pop(0)
        return value if self.dictionary else tuple(value)

    def fetchall(self):
        if not self._results:
            return []
        values = self._results
        self._results = []
        if self.dictionary:
            return [value for value in values]
        return [tuple(value) for value in values]

    def close(self):
        pass


class DummyNotifier:
    def __init__(self, *args, **kwargs):
        pass

    def send_combo_suggestions(self, combos):
        return None

    def send_restock_alerts(self, alerts):
        return None

    def send_offer_suggestions(self, suggestions):
        return None

    def send_top_product_notification(self, top_product):
        return None


@pytest.fixture()
def app_client(monkeypatch):
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
            sess['user_id'] = 99
            sess['role'] = 'admin'
            sess['name'] = 'Tester'
            sess['idle_minutes'] = 45
            sess['session_token'] = 'testing-token'
        yield client, fake_db


def test_sale_rejected_when_price_change_exceeds_without_force(app_client):
    client, fake_db = app_client
    payload = {
        'items': [{'id': 1, 'quantity': 1, 'price': 150.0}],
        'payment_method': 'efectivo',
        'force_price': False,
        'force_reason': '',
    }
    response = client.post('/api/ventas', json=payload)
    assert response.status_code == 409
    data = response.get_json()
    assert data['success'] is False
    assert fake_db.products[1]['stock'] == 10
    assert fake_db.ventas == []
    assert fake_db.price_audit == []


def test_sale_with_force_records_audit(app_client):
    client, fake_db = app_client
    payload = {
        'items': [{'id': 1, 'quantity': 1, 'price': 150.0}],
        'payment_method': 'tarjeta',
        'force_price': True,
        'force_reason': 'Cliente premium con acuerdo especial',
    }
    response = client.post('/api/ventas', json=payload)
    assert response.status_code == 200
    data = response.get_json()
    assert data['success'] is True
    assert pytest.approx(data['totals']['subtotal'], rel=1e-3) == 150.0
    assert pytest.approx(data['totals']['iva'], rel=1e-3) == 28.5
    assert pytest.approx(data['totals']['total'], rel=1e-3) == 178.5
    assert pytest.approx(data['total'], rel=1e-3) == 178.5
    assert fake_db.products[1]['stock'] == 9
    assert len(fake_db.ventas) == 1
    assert fake_db.ventas[0]['total'] == 178.5
    assert fake_db.ventas[0]['iva_percent'] == 19.0
    assert fake_db.venta_detalle[0]['precio'] == 150.0
    assert fake_db.venta_detalle[0]['iva_percent'] == 19.0
    assert fake_db.price_audit, 'Debe registrarse auditoria de precio forzado'
    audit_entry = fake_db.price_audit[0]
    assert audit_entry['precio_anterior'] == 100.0
    assert audit_entry['precio_nuevo'] == 150.0
    assert 'acuerdo especial' in (audit_entry['motivo'] or '').lower()
    assert len(fake_db.inventory_movements) == 1
    assert fake_db.inventory_movements[0]['tipo'] == 'salida'
    assert fake_db.inventory_movements[0]['cantidad'] == -1


def test_serialize_product_row_includes_individual_iva_fields():
    payload = app_module.serialize_product_row(
        {
            'nombre': 'Cafe Premium',
            'precio': '100.00',
            'iva_percent': '5.00',
            'stock': 4,
        }
    )

    assert payload['precio_base'] == pytest.approx(100.0)
    assert payload['iva_porcentaje'] == pytest.approx(5.0)
    assert payload['iva_valor'] == pytest.approx(5.0)
    assert payload['precio_con_iva'] == pytest.approx(105.0)


def test_sale_rolls_back_on_db_failure(app_client):
    client, fake_db = app_client
    fake_db.fail_on = 'venta_detalle'
    payload = {
        'items': [{'id': 1, 'quantity': 2, 'price': 120.0}],
        'payment_method': 'efectivo',
        'force_price': True,
        'force_reason': 'Ajuste acordado con el cliente',
    }
    response = client.post('/api/ventas', json=payload)
    assert response.status_code == 500
    data = response.get_json()
    assert data['success'] is False
    assert 'No se pudo registrar la venta' in data.get('message', '')
    assert fake_db.products[1]['stock'] == 10
    assert fake_db.ventas == []
    assert fake_db.venta_detalle == []
    assert fake_db.price_audit == []
    assert fake_db.inventory_movements == []


def test_sale_falls_back_to_configured_iva_rate(app_client, monkeypatch):
    client, fake_db = app_client
    fake_db.products[1]['iva_percent'] = None
    monkeypatch.setattr(app_module, 'get_configured_iva_percent', lambda cur: Decimal('16.00'))
    payload = {
        'items': [{'id': 1, 'quantity': 1}],
        'payment_method': 'efectivo',
        'force_price': False,
    }

    response = client.post('/api/ventas', json=payload)
    assert response.status_code == 200
    data = response.get_json()
    assert data['success'] is True
    assert pytest.approx(data['totals']['subtotal'], rel=1e-3) == 100.0
    assert pytest.approx(data['totals']['iva'], rel=1e-3) == 16.0
    assert pytest.approx(data['totals']['total'], rel=1e-3) == 116.0
    assert data['totals']['iva_percent'] == pytest.approx(16.0)
    assert fake_db.venta_detalle[0]['iva_percent'] == 16.0
    assert fake_db.ventas[0]['iva_percent'] == 16.0


def test_sale_prefers_product_specific_iva_rate(app_client, monkeypatch):
    client, fake_db = app_client
    fake_db.products[1]['iva_percent'] = '5.00'
    monkeypatch.setattr(app_module, 'get_configured_iva_percent', lambda cur: Decimal('19.00'))

    response = client.post(
        '/api/ventas',
        json={
            'items': [{'id': 1, 'quantity': 1}],
            'payment_method': 'efectivo',
            'force_price': False,
        },
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data['success'] is True
    assert data['totals']['subtotal'] == pytest.approx(100.0)
    assert data['totals']['iva'] == pytest.approx(5.0)
    assert data['totals']['total'] == pytest.approx(105.0)
    assert data['totals']['iva_percent'] == pytest.approx(5.0)
    assert data['totals']['iva_mode'] == 'global'
    assert fake_db.venta_detalle[0]['iva_percent'] == pytest.approx(5.0)
    assert fake_db.ventas[0]['iva_percent'] == pytest.approx(5.0)


def test_sale_detail_returns_iva_breakdown(app_client):
    client, _fake_db = app_client
    create_response = client.post(
        '/api/ventas',
        json={
            'items': [{'id': 1, 'quantity': 2}],
            'payment_method': 'nequi',
            'force_price': False,
        },
    )
    assert create_response.status_code == 200
    venta_id = create_response.get_json()['venta_id']

    detail_response = client.get(f'/api/ventas/{venta_id}')
    assert detail_response.status_code == 200
    data = detail_response.get_json()
    assert data['venta']['subtotal'] == pytest.approx(200.0)
    assert data['venta']['iva_total'] == pytest.approx(38.0)
    assert data['venta']['iva_porcentaje'] == pytest.approx(19.0)
    assert data['venta']['total'] == pytest.approx(238.0)
    assert len(data['items']) == 1
    assert data['items'][0]['iva_percent'] == pytest.approx(19.0)
    assert data['items'][0]['iva_total'] == pytest.approx(38.0)
    assert data['items'][0]['total_linea'] == pytest.approx(238.0)


def test_load_sale_detail_payload_uses_main_builder(monkeypatch):
    class DetailCursor:
        def __init__(self):
            self._one = None
            self._all = []

        def execute(self, query, params=None):
            normalized = " ".join(query.strip().lower().split())
            self._one = None
            self._all = []
            if normalized.startswith(
                "select v.id, v.fecha, v.total, v.metodo_pago, v.iva_percent,"
            ):
                self._one = {
                    "id": params[0],
                    "fecha": "2026-03-19T12:00:00",
                    "total": 238.0,
                    "metodo_pago": "efectivo",
                    "iva_percent": 19.0,
                    "usuario_id": 42,
                    "username": "tester42",
                    "name": "Tester 42",
                }
                return
            if normalized.startswith(
                "select vd.producto_id, p.nombre, vd.cantidad, vd.precio, vd.iva_percent"
            ):
                self._all = [
                    {
                        "producto_id": 1,
                        "nombre": "Cafe Premium",
                        "cantidad": 2,
                        "precio": 100.0,
                        "iva_percent": 19.0,
                    }
                ]
                return
            if normalized.startswith(
                "select combos, restock, estado from venta_recomendaciones"
            ):
                self._one = {"combos": "[]", "restock": "[]", "estado": "listo"}
                return
            raise AssertionError(f"Consulta inesperada: {normalized}")

        def fetchone(self):
            return self._one

        def fetchall(self):
            return self._all

    class DetailConnection:
        def cursor(self, dictionary=False):
            return DetailCursor()

    class CacheProbe:
        def __init__(self):
            self.online = False

        def mark_online(self):
            self.online = True

    cache_probe = CacheProbe()
    captured = {}

    monkeypatch.setattr(app_module, "OFFLINE_CACHE", cache_probe)
    monkeypatch.setattr(
        app_module,
        "build_sale_detail_payload",
        lambda venta, raw_items, rec_row: captured.update(
            {"venta": venta, "items": raw_items, "rec_row": rec_row}
        )
        or {"success": True, "custom": True},
    )

    payload = app_module.load_sale_detail_payload(DetailConnection(), 7)

    assert payload == {"success": True, "custom": True}
    assert captured["venta"]["id"] == 7
    assert captured["items"][0]["producto_id"] == 1
    assert captured["rec_row"]["estado"] == "listo"
    assert cache_probe.online is True


def test_inventory_movement_post_updates_stock(app_client):
    client, fake_db = app_client
    payload = {
        'product_id': 1,
        'tipo': 'entrada',
        'cantidad': 3,
        'motivo': 'Compra a proveedor',
    }
    response = client.post('/api/inventario/movimientos', json=payload)
    assert response.status_code == 200
    data = response.get_json()
    assert data['success'] is True
    assert fake_db.products[1]['stock'] == 13
    assert len(fake_db.inventory_movements) == 1
    movement = fake_db.inventory_movements[0]
    assert movement['tipo'] == 'entrada'
    assert movement['cantidad'] == 3
    assert movement['stock_anterior'] == 10
    assert movement['stock_nuevo'] == 13


def test_inventory_movement_post_rejects_negative_stock(app_client):
    client, fake_db = app_client
    payload = {
        'product_id': 1,
        'tipo': 'salida',
        'cantidad': 99,
        'motivo': 'Error de despacho',
    }
    response = client.post('/api/inventario/movimientos', json=payload)
    assert response.status_code == 409
    data = response.get_json()
    assert data['success'] is False
    assert 'stock negativo' in (data.get('error') or '').lower()
    assert fake_db.products[1]['stock'] == 10
    assert fake_db.inventory_movements == []


def test_inventory_movement_get_returns_rows_and_summary(app_client):
    client, _fake_db = app_client
    client.post('/api/inventario/movimientos', json={
        'product_id': 1,
        'tipo': 'entrada',
        'cantidad': 2,
        'motivo': 'Ingreso inicial',
    })
    client.post('/api/inventario/movimientos', json={
        'product_id': 1,
        'tipo': 'ajuste',
        'cantidad': -1,
        'motivo': 'Ajuste por conteo',
    })
    response = client.get('/api/inventario/movimientos?from=2026-01-01&to=2026-12-31')
    assert response.status_code == 200
    data = response.get_json()
    assert data['success'] is True
    assert len(data['movimientos']) == 2
    assert data['summary']['total'] == 2
    assert data['summary']['entrada'] == 1
    assert data['summary']['ajuste'] == 1
    assert data['summary']['salida'] == 0


def test_inventory_movement_requires_admin_role(app_client):
    client, _fake_db = app_client
    with client.session_transaction() as sess:
        sess['role'] = 'vendedor'
    response = client.get('/api/inventario/movimientos')
    assert response.status_code == 403
    data = response.get_json()
    assert 'error' in (data or {})
