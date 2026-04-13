import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
SRC_DIR = os.path.join(ROOT_DIR, 'src')
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

import pytest

from src import main as app_module


@pytest.fixture()
def admin_client(monkeypatch):
    monkeypatch.setattr(app_module, 'perform_sessions_cleanup', lambda conn=None: {'revoked': 5})
    monkeypatch.setattr(app_module, 'get_session_state', lambda *args, **kwargs: app_module.SessionState(True, False, False, None))
    app_module.app.config['TESTING'] = True
    monkeypatch.setattr(app_module, 'get_session_state', lambda *args, **kwargs: app_module.SessionState(True, False, False, None))
    with app_module.app.test_client() as client:
        with client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['role'] = 'admin'
            sess['name'] = 'Admin'
            sess['session_token'] = 'testing-token'
            sess['idle_minutes'] = 45
            sess['server_boot_id'] = app_module.SERVER_BOOT_ID
        yield client


def test_sessions_cleanup_endpoint_returns_stats(admin_client):
    response = admin_client.post('/api/sesiones/limpiar')
    assert response.status_code == 200
    data = response.get_json()
    assert data['success'] is True
    assert data['revoked'] == 5


def test_sessions_cleanup_requires_admin(monkeypatch):
    app_module.app.config['TESTING'] = True
    monkeypatch.setattr(app_module, 'get_session_state', lambda *args, **kwargs: app_module.SessionState(True, False, False, None))
    with app_module.app.test_client() as client:
        with client.session_transaction() as sess:
            sess['user_id'] = 2
            sess['role'] = 'vendedor'
            sess['session_token'] = 'testing-token'
            sess['idle_minutes'] = 45
            sess['server_boot_id'] = app_module.SERVER_BOOT_ID
        resp = client.post('/api/sesiones/limpiar')
        assert resp.status_code == 403
        data = resp.get_json()
        assert 'error' in (data or {})


def test_current_user_clears_stale_session_after_server_restart(monkeypatch):
    revoked_tokens = []
    app_module.app.config['TESTING'] = True
    monkeypatch.setattr(app_module, 'revoke_session_token', lambda token: revoked_tokens.append(token))

    with app_module.app.test_client() as client:
        with client.session_transaction() as sess:
            sess['user_id'] = 7
            sess['role'] = 'admin'
            sess['username'] = 'admin'
            sess['name'] = 'Administrador'
            sess['session_token'] = 'stale-token'
            sess['idle_minutes'] = 45
            sess['server_boot_id'] = 'boot-anterior'

        response = client.get('/api/current_user')
        assert response.status_code == 200
        assert response.get_json() == {'user': None}
        assert revoked_tokens == ['stale-token']

        with client.session_transaction() as sess:
            assert 'user_id' not in sess
            assert 'session_token' not in sess


class CleanupCursor:
    def __init__(self):
        self.rowcount = 3
        self.closed = False
        self.executed = []

    def execute(self, query, params=None):
        normalized = " ".join(query.strip().lower().split())
        self.executed.append((normalized, params))
        if "update sesiones_activas" not in normalized:
            raise AssertionError(f"Consulta inesperada: {normalized}")

    def close(self):
        self.closed = True


class CleanupConnection:
    def __init__(self):
        self.cursor_instance = CleanupCursor()
        self.commits = 0
        self.closed = False

    def cursor(self):
        return self.cursor_instance

    def commit(self):
        self.commits += 1

    def close(self):
        self.closed = True


def test_perform_sessions_cleanup_uses_main_dependencies(monkeypatch):
    fake_conn = CleanupConnection()
    ensured = {"called": False}

    monkeypatch.setattr(app_module, "get_db_conn", lambda: fake_conn)
    monkeypatch.setattr(
        app_module,
        "ensure_session_table",
        lambda cur: ensured.__setitem__("called", cur is fake_conn.cursor_instance),
    )

    stats = app_module.perform_sessions_cleanup()

    assert stats == {"revoked": 3}
    assert ensured["called"] is True
    assert fake_conn.commits == 1
    assert fake_conn.cursor_instance.closed is True
    assert fake_conn.closed is True


def test_finalize_login_session_uses_main_helpers(monkeypatch):
    stored = {}

    monkeypatch.setattr(app_module, "generate_session_token", lambda: "token-wrapper")
    monkeypatch.setattr(
        app_module,
        "store_session_token",
        lambda conn, token, user_id, role, idle_minutes, user_agent: stored.update(
            {
                "conn": conn,
                "token": token,
                "user_id": user_id,
                "role": role,
                "idle_minutes": idle_minutes,
                "user_agent": user_agent,
            }
        ),
    )
    monkeypatch.setattr(
        app_module,
        "get_session_state",
        lambda token, *args, **kwargs: app_module.SessionState(
            True, False, False, None
        ),
    )
    monkeypatch.setattr(
        app_module,
        "build_session_user_payload",
        lambda: {"id": 1, "username": "admin", "role": "admin", "marker": True},
    )

    with app_module.app.test_request_context(
        "/api/login", headers={"User-Agent": "pytest-agent"}
    ):
        payload = app_module.finalize_login_session(
            object(),
            {
                "id": 1,
                "username": "admin",
                "name": "Administrador",
                "role": "admin",
                "permissions": {},
            },
        )

        assert payload["success"] is True
        assert payload["session_token"] == "token-wrapper"
        assert payload["user"]["marker"] is True
        assert app_module.session["session_token"] == "token-wrapper"
        assert stored["token"] == "token-wrapper"
        assert stored["user_agent"] == "pytest-agent"


def test_require_permission_uses_main_permissions_helper(monkeypatch):
    monkeypatch.setattr(app_module, "require_login", lambda: None)
    monkeypatch.setattr(
        app_module,
        "get_session_permissions",
        lambda: {"dashboard_view": True},
    )

    with app_module.app.test_request_context("/api/dashboard"):
        app_module.session["role"] = "vendedor"
        result = app_module.require_permission("dashboard_view")

    assert result is None
