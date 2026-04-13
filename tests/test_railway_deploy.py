import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
SRC_DIR = os.path.join(ROOT_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from src import main as app_module


def test_build_db_config_from_env_supports_database_url():
    config = app_module.build_db_config_from_env(
        {
            "DATABASE_URL": "mysql://railway:secreta@mysql.railway.internal:3307/la_septima_estrella",
        }
    )

    assert config == {
        "host": "mysql.railway.internal",
        "port": 3307,
        "user": "railway",
        "password": "secreta",
        "database": "la_septima_estrella",
    }


def test_build_db_config_from_env_prefers_explicit_db_variables():
    config = app_module.build_db_config_from_env(
        {
            "DATABASE_URL": "mysql://railway:secreta@mysql.railway.internal:3307/la_septima_estrella",
            "DB_HOST": "127.0.0.1",
            "DB_PORT": "3306",
            "DB_USER": "root",
            "DB_PASSWORD": "",
            "DB_NAME": "tienda_local",
        }
    )

    assert config == {
        "host": "127.0.0.1",
        "port": 3306,
        "user": "root",
        "password": "",
        "database": "tienda_local",
    }


def test_resolve_backup_dir_uses_railway_volume_path():
    backup_dir = app_module.resolve_backup_dir(
        {"RAILWAY_VOLUME_MOUNT_PATH": "/data"}
    )

    assert backup_dir == "/data/backups"


def test_healthcheck_endpoint_returns_ok(monkeypatch):
    monkeypatch.setattr(app_module, "mysql_ping", lambda config, timeout=2: True)
    app_module.app.config["TESTING"] = True

    with app_module.app.test_client() as client:
        response = client.get("/healthz")

    assert response.status_code == 200
    assert response.get_json() == {
        "ok": True,
        "service": "la_septima_estrella",
        "db_online": True,
    }
