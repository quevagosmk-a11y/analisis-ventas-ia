import os
import sys
from datetime import datetime, timezone

import pytest

ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
SRC_DIR = os.path.join(ROOT_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from src import main as app_module


class StateFakeDB:
    def __init__(self):
        self.users = {
            1: {
                "id": 1,
                "username": "admin",
                "name": "Administrador",
                "role": "admin",
                "activo": 1,
            },
            2: {
                "id": 2,
                "username": "vendedor",
                "name": "Vendedor",
                "role": "vendedor",
                "activo": 1,
            },
        }
        self.products = {
            8: {
                "id": 8,
                "nombre": "Cafe Premium",
                "categoria": "Bebidas",
                "precio": 100.0,
                "iva_percent": 19.0,
                "stock": 8,
                "min_stock": 2,
                "activo": 1,
            }
        }


class StateFakeCursor:
    def __init__(self, db, dictionary=False):
        self.db = db
        self.dictionary = dictionary
        self._one = None
        self._all = []

    def execute(self, query, params=None):
        normalized = " ".join(query.strip().lower().split())
        self._one = None
        self._all = []
        if normalized.startswith("create table"):
            return
        if normalized.startswith("select id, username, name, role, activo from usuarios where id=%s"):
            row = self.db.users.get(params[0])
            self._one = dict(row) if row else None
            return
        if normalized.startswith("select id, role, activo from usuarios where id=%s"):
            row = self.db.users.get(params[0])
            if row:
                self._one = {"id": row["id"], "role": row["role"], "activo": row["activo"]}
            return
        if normalized.startswith("update usuarios set activo=%s where id=%s"):
            active, user_id = params
            self.db.users[user_id]["activo"] = int(active)
            return
        if normalized.startswith("update productos set activo=%s where id=%s"):
            active, product_id = params
            self.db.products[product_id]["activo"] = int(active)
            return
        raise AssertionError(f"Consulta inesperada: {normalized}")

    def fetchone(self):
        return self._one

    def fetchall(self):
        return self._all

    def close(self):
        pass


class StateFakeConnection:
    def __init__(self, db):
        self.db = db

    def cursor(self, dictionary=False):
        return StateFakeCursor(self.db, dictionary=dictionary)

    def commit(self):
        pass

    def close(self):
        pass


def _build_client(monkeypatch):
    monkeypatch.setattr(
        app_module,
        "get_session_state",
        lambda *args, **kwargs: app_module.SessionState(True, False, False, None),
    )
    app_module.app.config["TESTING"] = True
    client = app_module.app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = 1
        sess["role"] = "admin"
        sess["username"] = "admin"
        sess["name"] = "Administrador"
        sess["session_token"] = "testing-token"
        sess["idle_minutes"] = 45
        sess["last_activity"] = datetime.now(timezone.utc).isoformat()
    return client


@pytest.fixture()
def state_client(monkeypatch):
    fake_db = StateFakeDB()
    monkeypatch.setattr(app_module, "get_db_conn", lambda: StateFakeConnection(fake_db))
    monkeypatch.setattr(app_module, "ensure_users_table", lambda cur: None)
    monkeypatch.setattr(app_module, "count_active_admins", lambda cur: 2)
    with _build_client(monkeypatch) as client:
        yield client, fake_db


def test_product_state_endpoint_exists_and_records_audit(monkeypatch, state_client):
    client, fake_db = state_client
    audit_calls = []
    monkeypatch.setattr(app_module, "record_audit_event", lambda cur, **kwargs: audit_calls.append(kwargs) or 1)
    monkeypatch.setattr(app_module, "fetch_product", lambda conn, pid: dict(fake_db.products[pid]))

    response = client.put("/api/productos/8/estado", json={"activo": False})

    assert response.status_code == 200
    assert response.get_json()["success"] is True
    assert fake_db.products[8]["activo"] == 0
    assert audit_calls
    assert audit_calls[0]["event_type"] == "producto_estado_actualizado"


def test_user_state_endpoint_records_audit(monkeypatch, state_client):
    client, fake_db = state_client
    audit_calls = []
    monkeypatch.setattr(app_module, "record_audit_event", lambda cur, **kwargs: audit_calls.append(kwargs) or 1)

    response = client.put("/api/usuarios/2/estado", json={"activo": False})

    assert response.status_code == 200
    assert response.get_json()["success"] is True
    assert fake_db.users[2]["activo"] == 0
    assert audit_calls
    assert audit_calls[0]["event_type"] == "usuario_estado_actualizado"
