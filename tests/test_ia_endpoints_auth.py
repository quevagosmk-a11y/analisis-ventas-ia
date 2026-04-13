import os
import sys
from datetime import datetime, timezone

import pandas as pd
import pytest

ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
SRC_DIR = os.path.join(ROOT_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from src import main as app_module


@pytest.fixture()
def seller_client(monkeypatch):
    monkeypatch.setattr(
        app_module,
        "get_session_state",
        lambda *args, **kwargs: app_module.SessionState(True, False, False, None),
    )
    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as client:
        with client.session_transaction() as sess:
            sess["user_id"] = 2
            sess["role"] = "vendedor"
            sess["name"] = "Vendedor"
            sess["session_token"] = "testing-token"
            sess["idle_minutes"] = 45
            sess["last_activity"] = datetime.now(timezone.utc).isoformat()
        yield client


def sample_sales_df():
    return pd.DataFrame(
        {
            "product": ["Cafe", "Cafe", "Pan"],
            "category": ["Bebidas", "Bebidas", "Panaderia"],
            "qty": [2, 3, 4],
            "price": [3000.0, 3000.0, 1500.0],
            "total": [6000.0, 9000.0, 6000.0],
            "date": pd.to_datetime(["2025-01-01", "2025-01-02", "2025-01-02"]),
            "timestamp": pd.to_datetime(["2025-01-01", "2025-01-02", "2025-01-02"]),
            "payment_method": ["efectivo", "nequi", "efectivo"],
        }
    )


def test_ia_chat_requires_login(monkeypatch):
    monkeypatch.setattr(
        app_module,
        "get_session_state",
        lambda *args, **kwargs: app_module.SessionState(True, False, False, None),
    )
    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as client:
        response = client.post("/api/ia/chat", json={"question": "Que venderé?"})
    assert response.status_code == 401


def test_ia_chat_logged_user_ok(monkeypatch, seller_client):
    monkeypatch.setattr(app_module, "load_sales_dataframe_for_ai", lambda *args, **kwargs: sample_sales_df())
    monkeypatch.setattr(app_module, "fetch_inventory_snapshot", lambda: [])
    response = seller_client.post("/api/ia/chat", json={"question": "Dame un resumen de ventas"})
    assert response.status_code == 200
    payload = response.get_json()
    assert payload.get("answer")
    assert "insights" in payload


def test_ia_chat_greeting_returns_help(monkeypatch, seller_client):
    monkeypatch.setattr(
        app_module,
        "load_sales_dataframe_for_ai",
        lambda *args, **kwargs: sample_sales_df(),
    )
    monkeypatch.setattr(app_module, "fetch_inventory_snapshot", lambda: [])
    response = seller_client.post("/api/ia/chat", json={"question": "hola"})
    assert response.status_code == 200
    payload = response.get_json()
    assert "Puedo ayudarte con ventas" in (payload.get("answer") or "")
    assert "Acumulado analizado" not in (payload.get("answer") or "")


def test_ia_recommendations_returns_extended_payload(monkeypatch, seller_client):
    monkeypatch.setattr(app_module, "load_sales_dataframe_for_ai", lambda *args, **kwargs: sample_sales_df())
    monkeypatch.setattr(
        app_module,
        "fetch_inventory_snapshot",
        lambda: [{"id": 1, "nombre": "Cafe", "stock": 1, "min_stock": 2, "categoria": "Bebidas"}],
    )
    monkeypatch.setattr(
        app_module,
        "generate_ai_report",
        lambda *args, **kwargs: {
            "productos_alta_rotacion": [{"producto": "Cafe"}],
            "recomendaciones_reposicion": [{"producto": "Cafe", "compra_sugerida": 6}],
            "tendencias_predichas": [{"producto": "Cafe", "variacion_ventas": "+20%"}],
            "predicciones_demanda": {"Cafe": {"predicted_demand": 7.5}},
            "metadata": {"modelo_demanda": {"predicciones_disponibles": True}},
        },
    )
    response = seller_client.get("/api/ia/recomendaciones")
    assert response.status_code == 200
    payload = response.get_json()
    assert "top_product" in payload
    assert "recomendaciones_reposicion" in payload
    assert "predicciones_demanda" in payload
    assert "metadata" in payload


def test_ia_forecast_requires_admin_role(seller_client):
    response = seller_client.get("/api/ia/pronostico-demanda")
    assert response.status_code == 403
    payload = response.get_json()
    assert "error" in (payload or {})
