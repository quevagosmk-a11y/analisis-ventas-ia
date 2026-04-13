import json
import os
import sys
from datetime import datetime, timezone

import pytest

ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
SRC_DIR = os.path.join(ROOT_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from src import main as app_module


def _build_client(monkeypatch, role: str):
    monkeypatch.setattr(
        app_module,
        "get_session_state",
        lambda *args, **kwargs: app_module.SessionState(True, False, False, None),
    )
    app_module.app.config["TESTING"] = True
    client = app_module.app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = 1
        sess["role"] = role
        sess["name"] = role.title()
        sess["session_token"] = "testing-token"
        sess["idle_minutes"] = 45
        sess["last_activity"] = datetime.now(timezone.utc).isoformat()
    return client


@pytest.fixture()
def admin_client(monkeypatch):
    with _build_client(monkeypatch, "admin") as client:
        yield client


@pytest.fixture()
def seller_client(monkeypatch):
    with _build_client(monkeypatch, "vendedor") as client:
        yield client


class ConfigRolesFakeCursor:
    def __init__(self, connection, dictionary=False):
        self.connection = connection
        self.dictionary = dictionary
        self._one = None
        self._all = []

    def execute(self, query, params=None):
        normalized = " ".join(query.strip().lower().split())
        self._one = None
        self._all = []
        if normalized.startswith("create table if not exists configuracion_app"):
            return
        if normalized.startswith("create table if not exists roles_permisos"):
            return
        if normalized.startswith("drop table if exists roles_permisos"):
            self.connection.roles = {}
            return
        if normalized.startswith("show columns from roles_permisos like"):
            self._one = {"Field": params[0]}
            return
        if normalized.startswith("alter table roles_permisos add column"):
            return
        if normalized.startswith("update roles_permisos set name=role"):
            return
        if normalized.startswith("update roles_permisos set permissions_json"):
            return
        if normalized.startswith("update roles_permisos set permissions_json='{}'"):
            return
        if normalized.startswith(
            "select config_value from configuracion_app where config_key=%s limit 1"
        ):
            value = self.connection.config.get(params[0])
            self._one = {"config_value": value} if value is not None else None
            return
        if normalized.startswith("insert into configuracion_app (config_key, config_value)"):
            self.connection.config[params[0]] = str(params[1])
            return
        if normalized.startswith(
            "select role, name, permissions_json, is_system from roles_permisos where role=%s limit 1"
        ):
            role = params[0]
            row = self.connection.roles.get(role)
            self._one = dict(row) if row else None
            return
        if normalized.startswith("select role from roles_permisos where role=%s limit 1"):
            role = params[0]
            self._one = {"role": role} if role in self.connection.roles else None
            return
        if normalized.startswith("insert into roles_permisos (role, name, permissions_json, is_system)"):
            role, name, permissions_json, is_system = params
            self.connection.roles[role] = {
                "role": role,
                "name": name,
                "permissions_json": permissions_json,
                "is_system": int(is_system),
            }
            return
        if normalized.startswith(
            "select role, name, permissions_json, is_system from roles_permisos order by is_system desc, role asc"
        ):
            rows = sorted(
                self.connection.roles.values(),
                key=lambda item: (-int(item.get("is_system") or 0), item.get("role") or ""),
            )
            self._all = [dict(row) for row in rows]
            return
        raise AssertionError(f"Consulta inesperada: {normalized}")

    def fetchone(self):
        return self._one

    def fetchall(self):
        return self._all

    def close(self):
        pass


class ConfigRolesFakeConnection:
    def __init__(self):
        self.config = {}
        self.roles = {}

    def cursor(self, dictionary=False):
        return ConfigRolesFakeCursor(self, dictionary=dictionary)

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


def test_iva_config_get_and_put_work(monkeypatch, admin_client):
    fake_conn = ConfigRolesFakeConnection()
    monkeypatch.setattr(app_module, "get_db_conn", lambda: fake_conn)

    initial = admin_client.get("/api/config/iva")
    assert initial.status_code == 200
    initial_payload = initial.get_json()
    assert initial_payload["iva_percent"] == pytest.approx(19.0)
    assert initial_payload["allowed_payment_methods"] == [
        "efectivo",
        "nequi",
        "daviplata",
        "transferencia",
    ]

    updated = admin_client.put("/api/config/iva", json={"iva_percent": 16})
    assert updated.status_code == 200
    updated_payload = updated.get_json()
    assert updated_payload["success"] is True
    assert updated_payload["iva_percent"] == pytest.approx(16.0)

    reread = admin_client.get("/api/config/iva")
    assert reread.status_code == 200
    reread_payload = reread.get_json()
    assert reread_payload["iva_percent"] == pytest.approx(16.0)


def test_iva_config_put_requires_manage_permission(seller_client):
    response = seller_client.put("/api/config/iva", json={"iva_percent": 17})
    assert response.status_code == 403
    payload = response.get_json()
    assert "error" in (payload or {})


def test_roles_endpoint_lists_default_roles(monkeypatch, admin_client):
    fake_conn = ConfigRolesFakeConnection()
    monkeypatch.setattr(app_module, "get_db_conn", lambda: fake_conn)

    response = admin_client.get("/api/roles")

    assert response.status_code == 200
    payload = response.get_json()
    roles = payload["roles"]
    role_codes = [item["role"] for item in roles]
    assert role_codes[:4] == ["admin", "auditador", "gerente", "vendedor"]
    assert payload["permission_labels"]["ai_chat"] == "Usar asistente IA"


def test_roles_endpoint_creates_custom_role(monkeypatch, admin_client):
    fake_conn = ConfigRolesFakeConnection()
    monkeypatch.setattr(app_module, "get_db_conn", lambda: fake_conn)

    response = admin_client.post(
        "/api/roles",
        json={
            "role": "jefe_bodega",
            "name": "Jefe de Bodega",
            "permissions": {
                "dashboard_view": True,
                "products_view": True,
                "products_manage": True,
            },
        },
    )

    assert response.status_code == 201
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["role"] == "jefe_bodega"
    assert payload["name"] == "Jefe de Bodega"
    assert payload["permissions"]["products_manage"] is True
    assert payload["permissions"]["ai_chat"] is False

    listed = admin_client.get("/api/roles")
    listed_payload = listed.get_json()
    custom_role = next(
        item for item in listed_payload["roles"] if item["role"] == "jefe_bodega"
    )
    assert custom_role["name"] == "Jefe de Bodega"
    assert custom_role["permissions"]["products_manage"] is True
    saved_raw = fake_conn.roles["jefe_bodega"]["permissions_json"]
    assert json.loads(saved_raw)["products_manage"] is True
