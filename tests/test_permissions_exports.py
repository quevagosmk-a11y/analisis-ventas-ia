import os
import sys
from datetime import datetime, timezone
from types import SimpleNamespace

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


@pytest.fixture()
def auditor_client(monkeypatch):
    with _build_client(monkeypatch, "auditador") as client:
        yield client


class DashboardFakeCursor:
    def __init__(self, connection, dictionary=False):
        self.connection = connection
        self.dictionary = dictionary
        self._one = None
        self._all = []

    def execute(self, query, params=None):
        normalized = " ".join(query.strip().lower().split())
        self._one = None
        self._all = []
        self.connection.executed.append((normalized, params))
        if "as ventas_hoy" in normalized:
            self._one = {"ventas_hoy": 0.0}
            return
        if "as stock_bajo" in normalized:
            self._one = {"stock_bajo": 0}
            return
        if normalized == "select count(*) as total_productos from productos":
            self._one = {"total_productos": 28}
            return
        if "from venta_detalle vd" in normalized:
            self._all = [{"nombre": "Cafe", "total_vendido": 8}]
            return
        if normalized.startswith(
            "select id, nombre, stock, min_stock from productos"
        ):
            self._all = []
            return
        if "from ventas where date(fecha) between %s and %s" in normalized:
            self.connection.payment_params = params
            self._all = [
                {
                    "metodo_pago": "daviplata",
                    "total_ventas": 525,
                    "monto_total": 13287200.0,
                },
                {
                    "metodo_pago": "transferencia",
                    "total_ventas": 525,
                    "monto_total": 12892350.0,
                },
            ]
            return
        raise AssertionError(f"Consulta inesperada: {normalized}")

    def fetchone(self):
        return self._one

    def fetchall(self):
        return self._all


class DashboardFakeConnection:
    def __init__(self):
        self.executed = []
        self.payment_params = None

    def cursor(self, dictionary=False):
        return DashboardFakeCursor(self, dictionary=dictionary)

    def close(self):
        pass


def test_products_endpoint_requires_products_view(monkeypatch, auditor_client):
    monkeypatch.setattr(
        app_module,
        "get_db_conn",
        lambda: (_ for _ in ()).throw(AssertionError("No debe consultar BD")),
    )
    response = auditor_client.get("/api/productos")
    assert response.status_code == 403
    payload = response.get_json()
    assert "error" in (payload or {})


def test_seller_reports_endpoint_requires_reports_permission(monkeypatch, seller_client):
    monkeypatch.setattr(
        app_module,
        "load_sales_report_payload",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("No debe consultar reportes para vendedor")
        ),
    )
    response = seller_client.get("/api/reportes/ventas?from=2025-01-01&to=2025-01-31")
    assert response.status_code == 403
    payload = response.get_json()
    assert "error" in (payload or {})


def test_seller_report_export_requires_reports_permission(monkeypatch, seller_client):
    monkeypatch.setattr(
        app_module,
        "load_sales_report_payload",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("No debe exportar reportes para vendedor")
        ),
    )
    response = seller_client.get(
        "/api/reportes/ventas/export?from=2025-01-01&to=2025-01-31&format=pdf"
    )
    assert response.status_code == 403
    payload = response.get_json()
    assert "error" in (payload or {})


def test_report_export_endpoint_returns_pdf(monkeypatch, admin_client):
    monkeypatch.setattr(
        app_module,
        "load_sales_report_payload",
        lambda *_args, **_kwargs: {
            "success": True,
            "periodo": {"desde": "2025-01-01", "hasta": "2025-01-31"},
            "resumen": {
                "ventas_registradas": 1,
                "total_productos": 2,
                "monto_total": 18000.0,
            },
            "ventas": [
                {
                    "id": 9,
                    "fecha": "2025-01-10T12:00:00-05:00",
                    "vendedor": "admin",
                    "metodo_pago": "efectivo",
                    "items": 2,
                    "total": 18000.0,
                }
            ],
        },
    )
    response = admin_client.get(
        "/api/reportes/ventas/export?from=2025-01-01&to=2025-01-31&format=pdf"
    )
    assert response.status_code == 200
    assert response.mimetype == "application/pdf"
    assert response.data.startswith(b"%PDF")
    disposition = response.headers.get("Content-Disposition") or ""
    assert "reporte-ventas-2025-01-01-a-2025-01-31.pdf" in disposition


def test_stats_export_endpoint_returns_excel(monkeypatch, admin_client):
    monkeypatch.setattr(
        app_module,
        "load_product_stats_payload",
        lambda **_kwargs: {
            "success": True,
            "periodo": "rango_personalizado",
            "period": {"desde": "2025-01-01", "hasta": "2025-01-31"},
            "resumen": {
                "total_productos": 1,
                "total_unidades": 6,
                "monto_total": 24000.0,
            },
            "productos": [
                {"nombre": "Cafe", "cantidad": 6, "ingresos": 24000.0},
            ],
        },
    )
    response = admin_client.get(
        "/api/estadisticas/productos-mas-vendidos/export?from=2025-01-01&to=2025-01-31&format=excel"
    )
    assert response.status_code == 200
    assert (
        response.mimetype
        == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert len(response.data) > 20
    disposition = response.headers.get("Content-Disposition") or ""
    assert "reporte-estadisticas-2025-01-01-a-2025-01-31.xlsx" in disposition


def test_dashboard_returns_filtered_payment_breakdown(monkeypatch, admin_client):
    fake_conn = DashboardFakeConnection()
    monkeypatch.setattr(app_module, "get_db_conn", lambda: fake_conn)

    response = admin_client.get("/api/dashboard?from=2025-12-20&to=2026-03-19")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["payment_period"] == {
        "desde": "2025-12-20",
        "hasta": "2026-03-19",
    }
    assert len(payload["payment_breakdown"]) == 2
    assert payload["payment_breakdown"][0]["metodo_pago"] == "daviplata"
    assert payload["payment_breakdown"][0]["total_ventas"] == 525
    assert payload["payment_breakdown"][0]["monto_total"] == pytest.approx(
        13287200.0
    )
    assert fake_conn.payment_params == ("2025-12-20", "2026-03-19")


def test_load_dashboard_payload_uses_main_helpers(monkeypatch):
    class DirectDashboardCursor:
        def __init__(self, connection):
            self.connection = connection
            self._one = None
            self._all = []

        def execute(self, query, params=None):
            normalized = " ".join(query.strip().lower().split())
            self._one = None
            self._all = []
            if "as ventas_hoy" in normalized:
                self._one = {"ventas_hoy": 42000.0}
                return
            if "as stock_bajo" in normalized:
                self._one = {"stock_bajo": 1}
                return
            if normalized == "select count(*) as total_productos from productos":
                self._one = {"total_productos": 12}
                return
            if normalized.startswith("select count(*) as total from productos"):
                self._one = {"total": 1}
                return
            if "from venta_detalle vd" in normalized:
                self._all = [{"nombre": "Cafe", "total_vendido": 8}]
                return
            if normalized.startswith(
                "select id, nombre, stock, min_stock from productos"
            ):
                self._all = [{"id": 1, "nombre": "Cafe", "stock": 2, "min_stock": 5}]
                return
            if normalized.startswith("select id, nombre, categoria from productos"):
                self._all = [{"id": 1, "nombre": "Cafe", "categoria": "Bebidas"}]
                return
            if normalized.startswith("select m.id, m.producto_id, p.nombre as producto_nombre"):
                self._all = [
                    {
                        "id": 9,
                        "producto_id": 1,
                        "producto_nombre": "Cafe",
                        "tipo": "entrada",
                        "cantidad": 3,
                        "usuario": "admin",
                        "creado_en": "2026-03-19T10:00:00",
                    }
                ]
                return
            if "from ventas where date(fecha) between %s and %s" in normalized:
                self.connection.payment_params = params
                self._all = [
                    {
                        "metodo_pago": "efectivo",
                        "total_ventas": 2,
                        "monto_total": 42000.0,
                    }
                ]
                return
            raise AssertionError(f"Consulta inesperada: {normalized}")

        def fetchone(self):
            return self._one

        def fetchall(self):
            return self._all

    class DirectDashboardConnection:
        def __init__(self):
            self.payment_params = None

        def cursor(self, dictionary=False):
            return DirectDashboardCursor(self)

    state = {"online": False}
    monkeypatch.setattr(
        app_module,
        "OFFLINE_CACHE",
        SimpleNamespace(mark_online=lambda: state.__setitem__("online", True)),
    )
    monkeypatch.setattr(
        app_module,
        "enrich_product_with_alert",
        lambda row: {
            **row,
            "alert_level": "custom",
            "recommended_purchase": 7,
            "alert_badge_class": "bg-test",
            "alert_message": "revisar",
            "target_stock": 10,
        },
    )
    monkeypatch.setattr(
        app_module,
        "enrich_dashboard_payload",
        lambda payload, **kwargs: {
            **payload,
            "wrapper_flag": True,
            "products_source_count": len(kwargs["products_source"]),
            "movements_source_count": len(kwargs["movements_source"]),
        },
    )

    fake_conn = DirectDashboardConnection()
    payload = app_module.load_dashboard_payload(
        fake_conn,
        payment_period={"desde": "2025-12-20", "hasta": "2026-03-19"},
        payment_from="2025-12-20",
        payment_to="2026-03-19",
    )

    assert payload["wrapper_flag"] is True
    assert payload["products_source_count"] == 1
    assert payload["movements_source_count"] == 1
    assert payload["productos_stock_bajo"][0]["alert_level"] == "custom"
    assert payload["recomendaciones_compra"][0]["recomendar_comprar"] == 7
    assert fake_conn.payment_params == ("2025-12-20", "2026-03-19")
    assert state["online"] is True


class SalesReportCursor:
    def __init__(self):
        self._all = []

    def execute(self, query, params=None):
        normalized = " ".join(query.strip().lower().split())
        if "from ventas v" not in normalized:
            raise AssertionError(f"Consulta inesperada: {normalized}")
        assert params == ("2025-01-01", "2025-01-31")
        self._all = [
            {
                "id": 3,
                "fecha": "2025-01-10T12:00:00-05:00",
                "total": 18500.0,
                "metodo_pago": "efectivo",
                "vendedor": "admin",
                "items": 2,
            }
        ]

    def fetchall(self):
        return self._all

    def close(self):
        pass


class SalesReportConnection:
    def __init__(self):
        self.closed = False

    def cursor(self, dictionary=False):
        return SalesReportCursor()

    def close(self):
        self.closed = True


def test_load_sales_report_payload_uses_main_dependencies(monkeypatch):
    fake_conn = SalesReportConnection()
    offline_state = {"online": False, "offline": []}
    fake_cache = SimpleNamespace(
        mark_online=lambda: offline_state.__setitem__("online", True),
        mark_offline=lambda reason: offline_state["offline"].append(reason),
        get_sales_report=lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(app_module, "get_db_conn", lambda: fake_conn)
    monkeypatch.setattr(app_module, "OFFLINE_CACHE", fake_cache)
    monkeypatch.setattr(
        app_module,
        "build_ai_report_payload",
        lambda **_kwargs: {
            "metadata": {"fuente": "prueba"},
            "productos_alta_rotacion": [{"producto": "Cafe"}],
            "recomendaciones_reposicion": [],
            "tendencias_predichas": [],
            "predicciones_demanda": {},
        },
    )

    payload = app_module.load_sales_report_payload("2025-01-01", "2025-01-31")

    assert payload["success"] is True
    assert payload["resumen"]["ventas_registradas"] == 1
    assert payload["metadata"] == {"fuente": "prueba"}
    assert payload["productos_alta_rotacion"] == [{"producto": "Cafe"}]
    assert offline_state["online"] is True
    assert offline_state["offline"] == []
    assert fake_conn.closed is True
