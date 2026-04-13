import os
import sys
from datetime import datetime, timezone

import pytest

ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
SRC_DIR = os.path.join(ROOT_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from src import main as app_module


class FakeVoidDB:
    def __init__(self):
        self.products = {
            1: {"id": 1, "nombre": "Cafe", "stock": 3},
            2: {"id": 2, "nombre": "Pan", "stock": 7},
        }
        self.users = {
            1: {"id": 1, "username": "admin", "name": "Administrador"},
            7: {"id": 7, "username": "gerente", "name": "Gerente"},
            42: {"id": 42, "username": "vendedor", "name": "Vendedor"},
            77: {"id": 77, "username": "otro", "name": "Otro"},
        }
        self.sales = {
            10: {
                "id": 10,
                "fecha": "2026-04-04T10:00:00-05:00",
                "usuario_id": 42,
                "total": 238.0,
                "metodo_pago": "efectivo",
                "iva_percent": 19.0,
                "anulada": 0,
                "anulada_en": None,
                "anulada_por": None,
                "anulacion_motivo": None,
                "anulacion_autorizada": 0,
                "anulacion_autorizada_en": None,
                "anulacion_autorizada_por": None,
            },
            11: {
                "id": 11,
                "fecha": "2026-04-04T11:00:00-05:00",
                "usuario_id": 77,
                "total": 50.0,
                "metodo_pago": "nequi",
                "iva_percent": 19.0,
                "anulada": 0,
                "anulada_en": None,
                "anulada_por": None,
                "anulacion_motivo": None,
                "anulacion_autorizada": 0,
                "anulacion_autorizada_en": None,
                "anulacion_autorizada_por": None,
            },
        }
        self.sale_items = [
            {"venta_id": 10, "producto_id": 1, "cantidad": 2, "precio": 100.0, "iva_percent": 19.0},
            {"venta_id": 11, "producto_id": 2, "cantidad": 1, "precio": 42.0, "iva_percent": 19.0},
        ]
        self.inventory_movements = []
        self.audit_events = []


class FakeVoidConnection:
    def __init__(self, db):
        self.db = db

    def cursor(self, dictionary=False):
        return FakeVoidCursor(self.db, dictionary=dictionary)

    def start_transaction(self):
        return None

    def commit(self):
        return None

    def rollback(self):
        return None

    def close(self):
        return None


class FakeVoidCursor:
    def __init__(self, db, dictionary=False):
        self.db = db
        self.dictionary = dictionary
        self._one = None
        self._all = []
        self.lastrowid = 0

    def execute(self, query, params=None):
        normalized = " ".join(query.strip().lower().split())
        self._one = None
        self._all = []
        if normalized.startswith("show tables like"):
            self._all = [("ventas",)]
            return
        if normalized.startswith("show columns from") or normalized.startswith("show index from"):
            self._all = [("fake",)]
            return
        if normalized.startswith("create table") or normalized.startswith("alter table"):
            return
        if normalized.startswith("select v.id, v.fecha, v.total, v.metodo_pago, v.iva_percent"):
            sale_id = int(params[0])
            sale = self.db.sales.get(sale_id)
            if not sale:
                return
            user = self.db.users.get(sale["usuario_id"], {})
            self._one = {
                "id": sale["id"],
                "fecha": sale["fecha"],
                "total": sale["total"],
                "metodo_pago": sale["metodo_pago"],
                "iva_percent": sale["iva_percent"],
                "anulada": sale["anulada"],
                "anulada_en": sale["anulada_en"],
                "anulada_por": sale["anulada_por"],
                "anulacion_motivo": sale["anulacion_motivo"],
                "anulacion_autorizada": sale["anulacion_autorizada"],
                "anulacion_autorizada_en": sale["anulacion_autorizada_en"],
                "anulacion_autorizada_por": sale["anulacion_autorizada_por"],
                "usuario_id": user.get("id"),
                "username": user.get("username"),
                "name": user.get("name"),
            }
            return
        if normalized.startswith("select v.id, v.fecha, v.usuario_id, v.total"):
            sale_id = int(params[0])
            sale = self.db.sales.get(sale_id)
            if not sale:
                return
            user = self.db.users.get(sale["usuario_id"], {})
            self._one = {
                **sale,
                "username": user.get("username"),
                "name": user.get("name"),
            }
            return
        if normalized.startswith("select vd.producto_id, p.nombre, vd.cantidad, vd.precio, vd.iva_percent"):
            sale_id = int(params[0])
            self._all = [
                {
                    "producto_id": item["producto_id"],
                    "nombre": self.db.products[item["producto_id"]]["nombre"],
                    "cantidad": item["cantidad"],
                    "precio": item["precio"],
                    "iva_percent": item["iva_percent"],
                }
                for item in self.db.sale_items
                if item["venta_id"] == sale_id
            ]
            return
        if normalized.startswith("select combos, restock, estado from venta_recomendaciones"):
            return
        if normalized.startswith("select vd.producto_id, vd.cantidad, p.nombre"):
            sale_id = int(params[0])
            self._all = [
                {
                    "producto_id": item["producto_id"],
                    "cantidad": item["cantidad"],
                    "nombre": self.db.products[item["producto_id"]]["nombre"],
                }
                for item in self.db.sale_items
                if item["venta_id"] == sale_id
            ]
            return
        if normalized.startswith("select id, nombre, stock from productos where id=%s"):
            product_id = int(params[0])
            product = self.db.products.get(product_id)
            self._one = dict(product) if product else None
            return
        if normalized.startswith("update productos set stock=%s where id=%s"):
            stock, product_id = params
            self.db.products[int(product_id)]["stock"] = int(stock)
            return
        if normalized.startswith("update ventas set anulacion_autorizada=1"):
            actor_user_id, sale_id = params
            sale = self.db.sales[int(sale_id)]
            sale["anulacion_autorizada"] = 1
            sale["anulacion_autorizada_por"] = actor_user_id
            sale["anulacion_autorizada_en"] = "2026-04-04T12:00:00-05:00"
            return
        if normalized.startswith("update ventas set anulada=1"):
            actor_user_id, motivo, sale_id = params
            sale = self.db.sales[int(sale_id)]
            sale["anulada"] = 1
            sale["anulada_por"] = actor_user_id
            sale["anulada_en"] = "2026-04-04T12:05:00-05:00"
            sale["anulacion_motivo"] = motivo
            sale["anulacion_autorizada"] = 0
            return
        if normalized.startswith("insert into inventario_movimientos"):
            (
                producto_id,
                tipo,
                cantidad,
                stock_anterior,
                stock_nuevo,
                motivo,
                usuario_id,
            ) = params
            self.db.inventory_movements.append(
                {
                    "producto_id": producto_id,
                    "tipo": tipo,
                    "cantidad": cantidad,
                    "stock_anterior": stock_anterior,
                    "stock_nuevo": stock_nuevo,
                    "motivo": motivo,
                    "usuario_id": usuario_id,
                }
            )
            return
        if normalized.startswith("insert into auditoria_eventos"):
            (
                event_type,
                entity_type,
                entity_id,
                description,
                details_json,
                actor_user_id,
                actor_username,
            ) = params
            self.db.audit_events.append(
                {
                    "event_type": event_type,
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "description": description,
                    "details_json": details_json,
                    "actor_user_id": actor_user_id,
                    "actor_username": actor_username,
                }
            )
            return
        if normalized.startswith("select v.id, v.fecha, v.total, v.metodo_pago, v.usuario_id"):
            if "where v.usuario_id = %s" in normalized:
                viewer_user_id = int(params[0])
            else:
                viewer_user_id = None
            rows = []
            for sale in sorted(
                self.db.sales.values(),
                key=lambda item: (item["fecha"], item["id"]),
                reverse=True,
            ):
                if viewer_user_id is not None and int(sale["usuario_id"]) != viewer_user_id:
                    continue
                user = self.db.users.get(sale["usuario_id"], {})
                rows.append(
                    {
                        "id": sale["id"],
                        "fecha": sale["fecha"],
                        "total": sale["total"],
                        "metodo_pago": sale["metodo_pago"],
                        "usuario_id": sale["usuario_id"],
                        "anulada": sale["anulada"],
                        "anulacion_autorizada": sale["anulacion_autorizada"],
                        "vendedor": user.get("username"),
                        "vendedor_nombre": user.get("name"),
                    }
                )
            self._all = rows
            return
        raise AssertionError(f"Consulta inesperada: {normalized}")

    def fetchone(self):
        return self._one

    def fetchall(self):
        return list(self._all)

    def close(self):
        return None


def _build_client(monkeypatch, role: str, user_id: int):
    monkeypatch.setattr(
        app_module,
        "get_session_state",
        lambda *args, **kwargs: app_module.SessionState(True, False, False, None),
    )
    app_module.app.config["TESTING"] = True
    client = app_module.app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["role"] = role
        sess["username"] = app_module.coerce_user_role(role)
        sess["name"] = role.title()
        sess["session_token"] = "testing-token"
        sess["idle_minutes"] = 45
        sess["last_activity"] = datetime.now(timezone.utc).isoformat()
    return client


@pytest.fixture()
def fake_db():
    return FakeVoidDB()


@pytest.fixture()
def seller_client(monkeypatch, fake_db):
    monkeypatch.setattr(app_module, "get_db_conn", lambda: FakeVoidConnection(fake_db))
    with _build_client(monkeypatch, "vendedor", 42) as client:
        yield client


@pytest.fixture()
def manager_client(monkeypatch, fake_db):
    monkeypatch.setattr(app_module, "get_db_conn", lambda: FakeVoidConnection(fake_db))
    with _build_client(monkeypatch, "gerente", 7) as client:
        yield client


@pytest.fixture()
def admin_client(monkeypatch, fake_db):
    monkeypatch.setattr(app_module, "get_db_conn", lambda: FakeVoidConnection(fake_db))
    with _build_client(monkeypatch, "admin", 1) as client:
        yield client


def test_manager_can_authorize_sale_disable(manager_client, fake_db):
    response = manager_client.post(
        "/api/ventas/10/autorizar-deshabilitacion",
        json={"clave": "borrar"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert fake_db.sales[10]["anulacion_autorizada"] == 1
    assert fake_db.audit_events[-1]["event_type"] == "venta_anulacion_autorizada"


def test_seller_cannot_disable_without_authorization(seller_client, fake_db):
    response = seller_client.post("/api/ventas/10/deshabilitar", json={})

    assert response.status_code == 403
    payload = response.get_json()
    assert "autoriza" in (payload.get("error") or "").lower()
    assert fake_db.sales[10]["anulada"] == 0
    assert fake_db.products[1]["stock"] == 3


def test_seller_can_disable_authorized_sale_and_restore_stock(seller_client, fake_db):
    fake_db.sales[10]["anulacion_autorizada"] = 1

    response = seller_client.post(
        "/api/ventas/10/deshabilitar",
        json={"motivo": "Cobro equivocado"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert fake_db.sales[10]["anulada"] == 1
    assert fake_db.products[1]["stock"] == 5
    assert fake_db.inventory_movements[-1]["motivo"] == "Anulacion venta #10"
    assert fake_db.audit_events[-1]["event_type"] == "venta_deshabilitada"


def test_seller_can_disable_authorized_sale_from_another_user(seller_client, fake_db):
    fake_db.sales[11]["anulacion_autorizada"] = 1

    response = seller_client.post(
        "/api/ventas/11/deshabilitar",
        json={"motivo": "Venta registrada con error"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert fake_db.sales[11]["anulada"] == 1
    assert fake_db.products[2]["stock"] == 8
    assert fake_db.inventory_movements[-1]["motivo"] == "Anulacion venta #11"


def test_admin_can_disable_sale_without_previous_authorization(admin_client, fake_db):
    response = admin_client.post("/api/ventas/10/deshabilitar", json={})

    assert response.status_code == 200
    assert fake_db.sales[10]["anulada"] == 1


def test_sale_detail_includes_void_capabilities(seller_client, fake_db):
    fake_db.sales[10]["anulacion_autorizada"] = 1

    response = seller_client.get("/api/ventas/10")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["capabilities"]["can_void"] is True
    assert payload["capabilities"]["authorized_for_void"] is True


def test_seller_can_open_sale_detail_from_another_user(seller_client):
    response = seller_client.get("/api/ventas/11")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["venta"]["id"] == 11
    assert payload["capabilities"]["is_owner"] is False


def test_recent_sales_route_lists_all_sales_for_seller(seller_client):
    response = seller_client.get("/api/ventas/recientes")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert [row["id"] for row in payload["ventas"]] == [11, 10]
