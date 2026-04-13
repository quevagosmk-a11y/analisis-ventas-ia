import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
SRC_DIR = os.path.join(ROOT_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from src import main as app_module


def test_serve_index_injects_current_asset_version(monkeypatch):
    monkeypatch.setattr(
        app_module, "get_frontend_asset_version", lambda: "test-version"
    )
    app_module.app.config["TESTING"] = True

    with app_module.app.test_client() as client:
        response = client.get("/")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "style.css?v=test-version" in html
    assert "app.js?v=test-version" in html
    assert "__ASSET_VERSION__" not in html
    assert response.headers.get("Cache-Control") == "no-cache"
