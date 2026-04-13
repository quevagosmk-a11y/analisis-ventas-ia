import io
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest
from werkzeug.datastructures import FileStorage

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC_DIR = os.path.join(PROJECT_ROOT, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from src import main as app_module


class DummyConn:
    def close(self):
        return None

    def rollback(self):
        return None

    def commit(self):
        return None

    def cursor(self):
        return DummyCursor()


class DummyCursor:
    def __init__(self):
        self.executed = []

    def execute(self, query, params=None):
        self.executed.append((query, params))
        return None

    def close(self):
        return None


@pytest.fixture()
def admin_client(monkeypatch):
    monkeypatch.setattr(
        app_module,
        "get_session_state",
        lambda *args, **kwargs: app_module.SessionState(True, False, False, None),
    )
    client = app_module.app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = 1
        sess["username"] = "admin"
        sess["role"] = "admin"
        sess["name"] = "Administrador"
        sess["server_boot_id"] = app_module.SERVER_BOOT_ID
        sess["session_token"] = "testing-token"
        sess["permissions"] = {}
    return client


def test_login_rate_limit_blocks_after_repeated_failures(monkeypatch):
    app_module.LOGIN_ATTEMPTS.clear()
    app_module.LOGIN_LOCKOUTS.clear()
    monkeypatch.setattr(app_module, "get_db_conn", lambda: DummyConn())
    monkeypatch.setattr(
        app_module, "ensure_runtime_schema", lambda conn=None, force=False: True
    )
    monkeypatch.setattr(app_module, "ensure_seed_users", lambda conn: None)
    monkeypatch.setattr(
        app_module,
        "fetch_user_by_credentials",
        lambda conn, username, password: None,
    )
    monkeypatch.setattr(app_module, "try_record_audit_event", lambda *args, **kwargs: None)

    client = app_module.app.test_client()
    for _ in range(app_module.LOGIN_ATTEMPT_LIMIT - 1):
        response = client.post(
            "/api/login",
            json={"username": "admin", "password": "incorrecta"},
        )
        assert response.status_code == 401

    blocked = client.post(
        "/api/login",
        json={"username": "admin", "password": "incorrecta"},
    )
    payload = blocked.get_json()
    assert blocked.status_code == 429
    assert payload["success"] is False
    assert payload["seconds_left"] > 0


def test_get_login_throttle_seconds_left_uses_main_helpers(monkeypatch):
    app_module.LOGIN_ATTEMPTS.clear()
    app_module.LOGIN_LOCKOUTS.clear()
    called = {"pruned": False}

    monkeypatch.setattr(app_module, "build_login_attempt_key", lambda *_args: "custom-key")
    monkeypatch.setattr(
        app_module,
        "prune_login_throttle_state",
        lambda now=None: called.__setitem__("pruned", now is not None),
    )
    app_module.LOGIN_LOCKOUTS["custom-key"] = datetime.now(timezone.utc) + timedelta(
        seconds=45
    )

    seconds_left = app_module.get_login_throttle_seconds_left("admin", "127.0.0.1")

    assert seconds_left > 0
    assert called["pruned"] is True


def test_process_login_request_uses_main_helpers(monkeypatch):
    class LoginConn:
        def rollback(self):
            return None

        def close(self):
            return None

    audit_calls = []

    monkeypatch.setattr(app_module, "get_request_client_ip", lambda: "127.0.0.1")
    monkeypatch.setattr(
        app_module, "get_login_throttle_seconds_left", lambda *_args: 0
    )
    monkeypatch.setattr(app_module, "get_db_conn", lambda: LoginConn())
    monkeypatch.setattr(
        app_module, "ensure_runtime_schema", lambda conn: True
    )
    monkeypatch.setattr(app_module, "ensure_seed_users", lambda conn: None)
    monkeypatch.setattr(
        app_module,
        "fetch_user_by_credentials",
        lambda conn, username, password: {"id": 1, "username": username},
    )
    monkeypatch.setattr(app_module, "clear_login_attempts", lambda *_args: None)
    monkeypatch.setattr(
        app_module,
        "build_user_payload",
        lambda row: {
            "id": row["id"],
            "username": row["username"],
            "role": "admin",
            "name": "Administrador",
            "permissions": {},
        },
    )
    monkeypatch.setattr(
        app_module,
        "finalize_login_session",
        lambda conn, user_payload: {
            "success": True,
            "user": {**user_payload, "marker": True},
            "session_token": "token-wrapper",
            "idle_minutes": 60,
            "warning_seconds": app_module.SESSION_WARNING_SECONDS,
        },
    )
    monkeypatch.setattr(
        app_module,
        "try_record_audit_event",
        lambda conn, **kwargs: audit_calls.append(kwargs),
    )

    payload, status_code = app_module.process_login_request(
        {"username": "admin", "password": "Admin2026@"}
    )

    assert status_code == 200
    assert payload["user"]["marker"] is True
    assert payload["session_token"] == "token-wrapper"
    assert audit_calls
    assert audit_calls[0]["event_type"] == "login_exitoso"


def test_apply_schema_migrations_includes_sales_actor_foreign_keys(monkeypatch):
    conn = DummyConn()
    executed = []

    class MigrationCursor(DummyCursor):
        def execute(self, query, params=None):
            executed.append((query, params))
            return None

    monkeypatch.setattr(conn, "cursor", lambda: MigrationCursor())
    monkeypatch.setattr(app_module, "ensure_schema_migrations_table", lambda cur: None)
    monkeypatch.setattr(app_module, "list_applied_schema_migrations", lambda cur: set())

    migration_calls = []

    monkeypatch.setattr(
        app_module,
        "_run_core_schema_bootstrap",
        lambda cur, migration_conn: migration_calls.append("core") or {},
    )
    monkeypatch.setattr(
        app_module,
        "migrate_legacy_schema",
        lambda cur: migration_calls.append("legacy") or {},
    )
    monkeypatch.setattr(
        app_module,
        "migrate_foreign_keys",
        lambda cur: migration_calls.append("foreign_keys") or {},
    )
    monkeypatch.setattr(
        app_module,
        "_run_sales_void_schema_migration",
        lambda cur: migration_calls.append("sales_voiding") or {},
    )

    applied = app_module.apply_schema_migrations(conn)

    applied_versions = [item["version"] for item in applied]
    assert "20260405_sales_actor_foreign_keys" in applied_versions
    assert migration_calls == [
        "core",
        "legacy",
        "foreign_keys",
        "sales_voiding",
        "foreign_keys",
    ]
    assert any(
        params and params[0] == "20260405_sales_actor_foreign_keys"
        for _query, params in executed
    )


def test_manual_backup_endpoint_returns_artifacts(monkeypatch, admin_client):
    monkeypatch.setattr(
        app_module, "perform_backup", lambda reason="manual": "/tmp/snapshot-1.json"
    )
    monkeypatch.setattr(
        app_module,
        "build_backup_artifacts",
        lambda path, payload=None: {
            "json_filename": "snapshot-1.json",
            "json_url": "/api/backups/download/snapshot-1.json",
            "pdf_filename": "snapshot-1.pdf",
            "pdf_url": "/api/backups/download/snapshot-1.pdf",
        },
    )
    monkeypatch.setattr(app_module, "get_db_conn", lambda: DummyConn())
    monkeypatch.setattr(app_module, "try_record_audit_event", lambda *args, **kwargs: None)

    response = admin_client.post("/api/backups/manual")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["success"] is True
    assert payload["json_filename"] == "snapshot-1.json"
    assert payload["pdf_filename"] == "snapshot-1.pdf"


def test_restore_backup_endpoint_uses_restore_helper(monkeypatch, admin_client):
    called = {}

    monkeypatch.setattr(
        app_module,
        "resolve_backup_artifact_path",
        lambda filename: f"/tmp/{filename}",
    )

    def fake_restore(path, actor_user_id=None, actor_username=None):
        called["path"] = path
        called["actor_user_id"] = actor_user_id
        called["actor_username"] = actor_username
        return {"success": True, "json_filename": "snapshot-1.json"}

    monkeypatch.setattr(app_module, "restore_backup_snapshot", fake_restore)

    response = admin_client.post(
        "/api/backups/restore",
        json={"filename": "snapshot-1.json"},
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["success"] is True
    assert called["path"] == "/tmp/snapshot-1.json"
    assert called["actor_user_id"] == 1
    assert called["actor_username"] == "admin"


def test_build_backup_artifacts_uses_main_helpers(monkeypatch, tmp_path):
    snapshot_path = tmp_path / "snapshot-1.json"
    calls = {"loaded": False, "rendered": False}

    monkeypatch.setattr(app_module, "BACKUP_DIR", str(tmp_path))

    def fake_load(path):
        calls["loaded"] = path
        return {"metadata": {}, "productos": [], "ventas": []}

    def fake_pdf(payload):
        calls["rendered"] = payload
        return io.BytesIO(b"pdf-custom")

    monkeypatch.setattr(app_module, "load_backup_payload", fake_load)
    monkeypatch.setattr(app_module, "build_backup_pdf_file", fake_pdf)

    artifacts = app_module.build_backup_artifacts(str(snapshot_path))

    assert calls["loaded"] == str(snapshot_path)
    assert calls["rendered"] == {"metadata": {}, "productos": [], "ventas": []}
    assert artifacts["json_filename"] == "snapshot-1.json"
    assert artifacts["pdf_filename"] == "snapshot-1.pdf"
    assert (tmp_path / "snapshot-1.pdf").read_bytes() == b"pdf-custom"


def test_perform_backup_uses_main_serializer(monkeypatch, tmp_path):
    class FakeCache:
        def __init__(self):
            self.updated = None
            self.online = False
            self.offline = None

        def update(self, payload, source=None, path=None):
            self.updated = (payload, source, path)

        def mark_online(self):
            self.online = True

        def mark_offline(self, message):
            self.offline = message

    class BackupCursor:
        def __init__(self):
            self._all = []

        def execute(self, query, params=None):
            normalized = " ".join(query.strip().lower().split())
            if normalized.startswith("select id, nombre, categoria, precio, iva_percent, stock"):
                self._all = [
                    {
                        "id": 1,
                        "nombre": "Cafe",
                        "categoria": "Bebidas",
                        "precio": 3200.0,
                        "iva_percent": 19.0,
                        "stock": 5,
                        "min_stock": 2,
                        "activo": 1,
                        "imagen_mime": None,
                        "imagen_b64": None,
                    }
                ]
                return
            if normalized.startswith("select v.id, v.fecha, v.usuario_id, v.total"):
                self._all = [
                    {
                        "id": 10,
                        "fecha": "2026-03-20T10:00:00-05:00",
                        "usuario_id": 1,
                        "total": 6400.0,
                        "metodo_pago": "efectivo",
                        "iva_percent": 19.0,
                        "vendedor": "admin",
                    }
                ]
                return
            if normalized.startswith("select vd.id, vd.venta_id, vd.producto_id"):
                self._all = [
                    {
                        "id": 15,
                        "venta_id": 10,
                        "producto_id": 1,
                        "producto": "Cafe",
                        "cantidad": 2,
                        "precio": 3200.0,
                        "iva_percent": 19.0,
                    }
                ]
                return
            if normalized.startswith("select config_key, config_value, updated_at"):
                self._all = [{"config_key": "demo", "config_value": "1", "updated_at": None}]
                return
            if normalized.startswith("select m.id, m.producto_id, p.nombre as producto_nombre"):
                self._all = [
                    {
                        "id": 99,
                        "producto_id": 1,
                        "producto_nombre": "Cafe",
                        "tipo": "entrada",
                        "cantidad": 3,
                        "stock_anterior": 2,
                        "stock_nuevo": 5,
                        "motivo": "reposicion",
                        "usuario_id": 1,
                        "usuario": "admin",
                        "creado_en": "2026-03-19T09:00:00-05:00",
                    }
                ]
                return
            raise AssertionError(f"Consulta inesperada: {normalized}")

        def fetchall(self):
            return self._all

    class BackupConn:
        def cursor(self, dictionary=False):
            return BackupCursor()

        def close(self):
            return None

    fake_cache = FakeCache()
    snapshot_dir = tmp_path / "backups"
    serialized_rows = []

    monkeypatch.setattr(app_module, "BACKUP_DIR", str(snapshot_dir))
    monkeypatch.setattr(app_module, "OFFLINE_CACHE", fake_cache)
    monkeypatch.setattr(app_module, "get_db_conn", lambda: BackupConn())
    monkeypatch.setattr(
        app_module, "ensure_backup_dir", lambda: snapshot_dir.mkdir(exist_ok=True)
    )
    monkeypatch.setattr(app_module, "prune_old_backups", lambda: None)

    def fake_serialize(row):
        serialized_rows.append(row["nombre"])
        payload = dict(row)
        payload["serializado"] = True
        return payload

    monkeypatch.setattr(app_module, "serialize_product_row", fake_serialize)

    snapshot_path = app_module.perform_backup(reason="test-wrapper")

    assert snapshot_path is not None
    assert serialized_rows == ["Cafe"]
    with open(snapshot_path, "r", encoding="utf-8") as fh:
        payload = json.load(fh)
    assert payload["productos"][0]["serializado"] is True
    assert fake_cache.updated[1] == "backup"
    assert fake_cache.online is True


def test_restore_backup_snapshot_uses_main_loader(monkeypatch):
    class FakeCache:
        def __init__(self):
            self.updated = None
            self.online = False

        def update(self, payload, source=None, path=None):
            self.updated = (payload, source, path)

        def mark_online(self):
            self.online = True

    class RestoreCursor:
        def __init__(self):
            self.executed = []

        def execute(self, query, params=None):
            self.executed.append((" ".join(query.strip().lower().split()), params))

        def close(self):
            return None

    class RestoreConn:
        def __init__(self):
            self.cursor_obj = RestoreCursor()
            self.started = False
            self.committed = False
            self.closed = False

        def cursor(self, dictionary=False):
            return self.cursor_obj

        def start_transaction(self):
            self.started = True

        def commit(self):
            self.committed = True

        def rollback(self):
            return None

        def close(self):
            self.closed = True

    fake_cache = FakeCache()
    fake_conn = RestoreConn()
    called = {"loaded": None}
    audit_calls = []

    monkeypatch.setattr(app_module, "OFFLINE_CACHE", fake_cache)
    monkeypatch.setattr(app_module, "get_db_conn", lambda: fake_conn)
    monkeypatch.setattr(
        app_module, "ensure_runtime_schema", lambda conn, force=False: True
    )
    monkeypatch.setattr(
        app_module,
        "load_backup_payload",
        lambda path: called.update({"loaded": path}) or {"metadata": {"productos": 0}},
    )
    monkeypatch.setattr(
        app_module, "record_audit_event", lambda cur, **kwargs: audit_calls.append(kwargs)
    )

    result = app_module.restore_backup_snapshot(
        "/tmp/snapshot-wrapper.json",
        actor_user_id=1,
        actor_username="admin",
    )

    assert called["loaded"] == "/tmp/snapshot-wrapper.json"
    assert result["success"] is True
    assert result["json_filename"] == "snapshot-wrapper.json"
    assert fake_conn.started is True
    assert fake_conn.committed is True
    assert fake_conn.closed is True
    assert fake_cache.updated[1] == "backup-restore"
    assert fake_cache.online is True
    assert audit_calls
    assert audit_calls[0]["actor_user_id"] == 1
    assert audit_calls[0]["actor_username"] == "admin"


def test_inventory_export_endpoint_returns_csv(monkeypatch, admin_client):
    monkeypatch.setattr(app_module, "get_db_conn", lambda: DummyConn())
    monkeypatch.setattr(
        app_module, "ensure_runtime_schema", lambda conn=None, force=False: True
    )
    monkeypatch.setattr(
        app_module,
        "fetch_exportable_products",
        lambda conn: [
            {
                "id": 1,
                "nombre": "Arroz",
                "categoria": "Granos",
                "precio": 3200,
                "iva_percent": 5,
                "stock": 12,
                "min_stock": 4,
                "activo": 1,
                "imagen_data_url": "",
                "creado_en": None,
            }
        ],
    )
    monkeypatch.setattr(app_module, "try_record_audit_event", lambda *args, **kwargs: None)

    response = admin_client.get("/api/productos/export?format=csv")

    assert response.status_code == 200
    assert "inventario-productos.csv" in response.headers.get(
        "Content-Disposition", ""
    )
    assert b"Arroz" in response.data


def test_inventory_export_endpoint_returns_pdf(monkeypatch, admin_client):
    monkeypatch.setattr(app_module, "get_db_conn", lambda: DummyConn())
    monkeypatch.setattr(
        app_module, "ensure_runtime_schema", lambda conn=None, force=False: True
    )
    monkeypatch.setattr(
        app_module,
        "fetch_exportable_products",
        lambda conn: [
            {
                "id": 1,
                "nombre": "Arroz",
                "categoria": "Granos",
                "precio": 3200,
                "iva_percent": 5,
                "stock": 12,
                "min_stock": 4,
                "activo": 1,
                "imagen_data_url": "",
                "creado_en": None,
            }
        ],
    )
    monkeypatch.setattr(app_module, "try_record_audit_event", lambda *args, **kwargs: None)

    response = admin_client.get("/api/productos/export?format=pdf")

    assert response.status_code == 200
    assert "inventario-productos.pdf" in response.headers.get(
        "Content-Disposition", ""
    )
    assert response.headers.get("Content-Type", "").startswith("application/pdf")


def test_load_inventory_import_rows_parses_csv():
    content = (
        "nombre,categoria,precio,stock,min_stock,iva_percent,activo\n"
        "Arroz,Granos,3200,15,5,5,1\n"
    ).encode("utf-8")
    file_storage = FileStorage(
        stream=io.BytesIO(content),
        filename="inventario.csv",
        content_type="text/csv",
    )

    rows = app_module.load_inventory_import_rows(
        file_storage, app_module.DEFAULT_IVA_PERCENT
    )

    assert len(rows) == 1
    assert rows[0]["nombre"] == "Arroz"
    assert rows[0]["categoria"] == "Granos"
    assert rows[0]["precio"] == 3200.0
    assert rows[0]["iva_percent"] == 5.0
    assert rows[0]["activo"] == 1


def test_enrich_dashboard_payload_adds_operational_indicators():
    payload = app_module.enrich_dashboard_payload(
        {
            "productos_stock_bajo": [
                {"alert_level": "critico"},
                {"alert_level": "alto"},
            ]
        },
        products_source=[
            {"id": 1, "nombre": "Arroz", "categoria": "Granos", "imagen_url": ""},
            {
                "id": 2,
                "nombre": "Leche",
                "categoria": "Lacteos",
                "imagen_url": "data:image/png;base64,abc",
            },
        ],
        movements_source=[
            {
                "id": 9,
                "producto_id": 1,
                "producto_nombre": "Arroz",
                "tipo": "entrada",
                "cantidad": 3,
                "usuario": "admin",
                "creado_en": "2026-03-19T10:00:00",
            }
        ],
    )

    assert payload["stock_critico"] == 1
    assert payload["productos_sin_imagen"] == 1
    assert payload["productos_sin_imagen_detalle"][0]["nombre"] == "Arroz"
    assert payload["movimientos_recientes"][0]["producto_nombre"] == "Arroz"


def test_product_needs_stock_alert_includes_near_minimum_follow_up():
    product = {"stock": 11, "min_stock": 10}

    assert app_module.product_needs_stock_alert(product) is True

    enriched = app_module.enrich_product_with_alert(product)
    assert enriched["alert_level"] == "seguimiento"
    assert enriched["alert_message"] == "Muy cerca del mínimo."
