import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
SRC_DIR = os.path.join(ROOT_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from src import main as app_module


def test_normalize_user_role_accepts_system_and_custom_roles():
    assert app_module.normalize_user_role("admin") == "admin"
    assert app_module.normalize_user_role("VENDEDOR") == "vendedor"
    assert app_module.normalize_user_role("jefe_bodega") == "jefe_bodega"


def test_normalize_user_role_rejects_invalid_pattern():
    try:
        app_module.normalize_user_role("12")
        raise AssertionError("Se esperaba ValueError para rol invalido")
    except ValueError as exc:
        assert "Rol invalido" in str(exc)


def test_coerce_user_role_falls_back_to_vendedor():
    assert app_module.coerce_user_role("12") == "vendedor"
    assert app_module.coerce_user_role(None) == "vendedor"


def test_build_user_payload_preserves_custom_role():
    payload = app_module.build_user_payload(
        {
            "id": 7,
            "username": "legacy_user",
            "name": "Legacy",
            "role": "jefe_bodega",
        }
    )
    assert payload["role"] == "jefe_bodega"
    assert isinstance(payload["permissions"], dict)


def test_vendor_default_permissions_exclude_reports():
    permissions = app_module.default_role_permissions("vendedor")
    assert permissions["sales_view"] is True
    assert permissions["reports_view"] is False


def test_setup_users_cli_creates_admin_and_seller(monkeypatch):
    calls = []

    class DummyConn:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

    conn = DummyConn()
    monkeypatch.setattr(app_module, "get_db_conn", lambda: conn)

    def fake_reset_user_password(connection, username, password, **kwargs):
        calls.append(
            {
                "connection": connection,
                "username": username,
                "password": password,
                "role": kwargs.get("role"),
                "name": kwargs.get("name"),
                "activate": kwargs.get("activate"),
            }
        )
        return {"id": len(calls), "username": username, "created": False}

    monkeypatch.setattr(app_module, "reset_user_password", fake_reset_user_password)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "main.py",
            "setup_users",
            "--admin-pass=Admin2026@",
            "--seller-pass=Vendedor2026@",
        ],
    )

    result = app_module.main_setup_users_cli()
    assert result == 0
    assert conn.closed is True
    assert len(calls) == 2
    assert calls[0]["username"] == "admin"
    assert calls[0]["role"] == "admin"
    assert calls[1]["username"] == "vendedor"
    assert calls[1]["role"] == "vendedor"


def test_setup_users_cli_rejects_same_username(monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "main.py",
            "setup_users",
            "--admin-user=operador",
            "--seller-user=operador",
        ],
    )
    result = app_module.main_setup_users_cli()
    assert result == 1
