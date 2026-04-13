from __future__ import annotations

import argparse
import base64
import csv
import io
import json
import math
import os
import re
import secrets
import sys
import threading
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import unquote, urlparse

import pandas as pd
from flasgger import Swagger
from flask import (
    Flask,
    has_request_context,
    jsonify,
    redirect,
    request,
    send_file,
    send_from_directory,
    session,
)
from flask_cors import CORS
from fpdf import FPDF
from openpyxl import Workbook

from ai import chat_queries as chat_query_utils
from ai import chat_responses as chat_response_utils
from ai import generate_ai_report
from ai.engine import AIEngineConfig
from analysis import audit_trail as audit_trail_utils
from analysis import dashboard_data as dashboard_data_utils
from analysis import report_exports as report_export_utils
from analysis import reporting as reporting_utils
from analysis import sale_details as sale_detail_utils
from analysis import sale_voiding as sale_void_utils
from analysis.recommender import Recommender
from data.sales_loader import load_sales_data, load_sales_from_db
from db import connect as mysql_connect, ping as mysql_ping
from db.roles import (
    ROLE_PERMISSION_LABELS,
    coerce_user_role,
    count_active_admins,
    default_role_permissions,
    ensure_default_role_definitions,
    ensure_roles_permissions_table,
    fetch_role_definition,
    normalize_permissions_map,
    normalize_user_role,
    role_display_name,
    role_exists,
    save_role_definition,
)
from db.schema_tools import migrate_foreign_keys, migrate_legacy_schema
from messaging.notifier import Notifier
from utils import auth_flow as auth_flow_utils
from utils import auth_guards as auth_guard_utils
from utils import auth_session as auth_session_utils
from utils import backup_files as backup_file_utils
from utils import backup_runtime as backup_runtime_utils
from utils import dashboard_helpers as dashboard_helper_utils
from utils import session_core as session_core_utils
from utils.audit import build_product_update_audit_description
from utils.numeric import parse_decimal, parse_int
from utils.offline import OFFLINE_CACHE
from utils.security import (
    PASSWORD_HASH_SCHEME as PASSWORD_HASH_SCHEME_STRICT,
)
from utils.security import (
    enforce_password_policy as enforce_password_policy_strict,
)
from utils.security import (
    hash_password as hash_password_strict,
)
from utils.security import (
    needs_password_rehash,
    verify_password,
)

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - Python < 3.9
    from backports.zoneinfo import ZoneInfo  # type: ignore

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - dependencia opcional
    load_dotenv = None  # type: ignore


if load_dotenv:
    PROJECT_ROOT = Path(__file__).resolve().parents[1]
    # Cargar .env sin pisar variables del entorno actual.
    # Asi PowerShell/CMD puede sobrescribir credenciales cuando sea necesario.
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    load_dotenv(PROJECT_ROOT / ".env.local", override=False)

BOGOTA_TZ = ZoneInfo("America/Bogota")
PASSWORD_HASH_SCHEME = PASSWORD_HASH_SCHEME_STRICT
normalize_query_text = chat_query_utils.normalize_query_text
format_currency_basic = chat_query_utils.format_currency_basic
build_price_lookup_from_sales = chat_query_utils.build_price_lookup_from_sales
find_products_in_question = chat_query_utils.find_products_in_question
resolve_period = chat_query_utils.resolve_period
answer_sales_summary = chat_query_utils.answer_sales_summary
answer_restock_question = chat_query_utils.answer_restock_question
answer_top_products_question = chat_query_utils.answer_top_products_question
answer_payment_method_question = chat_query_utils.answer_payment_method_question
is_stock_question = chat_query_utils.is_stock_question
is_combo_question = chat_query_utils.is_combo_question
answer_stock_query = chat_query_utils.answer_stock_query
answer_combo_query = chat_query_utils.answer_combo_query
build_chat_help_response = chat_response_utils.build_chat_help_response
answer_chat_smalltalk = chat_response_utils.answer_chat_smalltalk
is_operational_question = chat_response_utils.is_operational_question
compose_chat_answer = chat_response_utils.compose_chat_answer
parse_requested_date_range = reporting_utils.parse_requested_date_range
summarize_sales_report_rows = reporting_utils.summarize_sales_report_rows
build_payment_breakdown_from_sales = reporting_utils.build_payment_breakdown_from_sales
fetch_sales_report_rows = reporting_utils.fetch_sales_report_rows
summarize_product_statistics_rows = reporting_utils.summarize_product_statistics_rows
fetch_product_statistics_rows = reporting_utils.fetch_product_statistics_rows
normalize_audit_event_type = audit_trail_utils.normalize_audit_event_type
resolve_audit_action_filter = audit_trail_utils.resolve_audit_action_filter
parse_int_limit = audit_trail_utils.parse_int_limit
parse_json_object = audit_trail_utils.parse_json_object
build_audit_actor_label = audit_trail_utils.build_audit_actor_label
build_audit_entity_label = audit_trail_utils.build_audit_entity_label
normalize_export_format = report_export_utils.normalize_export_format
build_purchase_recommendations = dashboard_data_utils.build_purchase_recommendations
SessionState = session_core_utils.SessionState
cleanup_expired_sessions = session_core_utils.cleanup_expired_sessions
normalize_lookup_text = dashboard_helper_utils.normalize_lookup_text
enrich_product_with_alert = dashboard_helper_utils.enrich_product_with_alert
product_needs_stock_alert = dashboard_helper_utils.product_needs_stock_alert
build_products_without_image_rows = (
    dashboard_helper_utils.build_products_without_image_rows
)
build_recent_movements_rows = dashboard_helper_utils.build_recent_movements_rows
enrich_dashboard_payload = dashboard_helper_utils.enrich_dashboard_payload

def _read_env_non_empty(
    env: Dict[str, str] | os._Environ[str], *keys: str
) -> Optional[str]:
    for key in keys:
        value = env.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _read_env_allow_empty(
    env: Dict[str, str] | os._Environ[str], *keys: str
) -> Optional[str]:
    for key in keys:
        if key not in env:
            continue
        value = env.get(key)
        if value is None:
            continue
        return str(value)
    return None


def parse_mysql_connection_url(raw_url: Optional[str]) -> Dict[str, Any]:
    url = str(raw_url or "").strip()
    if not url:
        return {}
    parsed = urlparse(url)
    scheme = (parsed.scheme or "").split("+", 1)[0].lower()
    if scheme not in {"mysql", "mariadb"}:
        return {}
    database_name = unquote((parsed.path or "").lstrip("/")).strip() or None
    return {
        "host": parsed.hostname or None,
        "port": parsed.port or 3306,
        "user": unquote(parsed.username) if parsed.username else None,
        "password": unquote(parsed.password) if parsed.password else None,
        "database": database_name,
    }


def build_db_config_from_env(
    env: Optional[Dict[str, str] | os._Environ[str]] = None,
) -> Dict[str, Any]:
    env_map = os.environ if env is None else env
    url_config = parse_mysql_connection_url(
        _read_env_non_empty(env_map, "DB_URL", "DATABASE_URL", "MYSQL_URL")
    )
    host = (
        _read_env_non_empty(env_map, "DB_HOST", "MYSQLHOST")
        or url_config.get("host")
        or "127.0.0.1"
    )
    port_value = (
        _read_env_non_empty(env_map, "DB_PORT", "MYSQLPORT")
        or str(url_config.get("port") or "3306")
    )
    user = (
        _read_env_non_empty(env_map, "DB_USER", "MYSQLUSER")
        or url_config.get("user")
        or "root"
    )
    password = _read_env_allow_empty(env_map, "DB_PASSWORD", "MYSQLPASSWORD")
    if password is None:
        password = str(url_config.get("password") or "")
    database_name = (
        _read_env_non_empty(env_map, "DB_NAME", "MYSQLDATABASE")
        or url_config.get("database")
        or "la_septima_estrella"
    )
    return {
        # En Windows/XAMPP suele ser mas estable usar 127.0.0.1 en vez de localhost.
        "host": host,
        "port": int(str(port_value).strip() or "3306"),
        "user": user,
        "password": password,
        "database": database_name,
    }


def resolve_backup_dir(
    env: Optional[Dict[str, str] | os._Environ[str]] = None,
) -> str:
    env_map = os.environ if env is None else env
    explicit_dir = _read_env_non_empty(env_map, "APP_BACKUP_DIR")
    if explicit_dir:
        return explicit_dir
    railway_mount = _read_env_non_empty(env_map, "RAILWAY_VOLUME_MOUNT_PATH")
    if railway_mount:
        return str(Path(railway_mount) / "backups")
    return "backups"


DB_CONFIG = build_db_config_from_env()

app = Flask(__name__)
app.secret_key = os.environ.get("APP_SECRET_KEY") or secrets.token_urlsafe(32)
CORS(app, supports_credentials=True)
app.config["SWAGGER"] = {
    "title": "La Septima Estrella API",
    "uiversion": 3,
}
swagger = Swagger(app)
SERVER_BOOT_ID = secrets.token_hex(16)

SESSION_IDLE_TIMEOUT_MINUTES = max(
    1, int(os.environ.get("SESSION_IDLE_TIMEOUT_MINUTES", "360"))
)
SESSION_MAX_AGE_DAYS = max(1, int(os.environ.get("SESSION_MAX_AGE_DAYS", "5")))
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=SESSION_MAX_AGE_DAYS)
app.config["SESSION_COOKIE_SAMESITE"] = os.environ.get("SESSION_COOKIE_SAMESITE", "Lax")
app.config["SESSION_COOKIE_SECURE"] = (
    os.environ.get("SESSION_COOKIE_SECURE", "0") == "1"
)

PRICE_MIN = Decimal("0.01")
PRICE_MAX = Decimal("1000000")
STOCK_MIN = 0
STOCK_MAX = 1000000
IVA_MIN = Decimal("0")
IVA_MAX = Decimal("100")
PRICE_STEP = Decimal("0.01")
DEFAULT_IVA_PERCENT = Decimal(os.environ.get("DEFAULT_IVA_PERCENT", "19"))
PRICE_CHANGE_MAX_RATIO = float(os.environ.get("PRICE_CHANGE_MAX_RATIO", "0.4"))
PRICE_FORCE_REASON_MIN_LENGTH = max(
    5, int(os.environ.get("PRICE_FORCE_REASON_MIN_LENGTH", "10"))
)
ROLE_IDLE_TIMEOUTS = {
    "admin": int(os.environ.get("SESSION_IDLE_TIMEOUT_ADMIN", "360")),
    "vendedor": int(os.environ.get("SESSION_IDLE_TIMEOUT_SELLER", "360")),
}
SESSION_WARNING_SECONDS = int(os.environ.get("SESSION_WARNING_SECONDS", "300"))
PASSWORD_MIN_LENGTH = max(8, int(os.environ.get("PASSWORD_MIN_LENGTH", "8")))
DEFAULT_ADMIN_PASSWORD = os.environ.get("DEFAULT_ADMIN_PASSWORD", "Admin2026@")
DEFAULT_VENDOR_PASSWORD = os.environ.get("DEFAULT_VENDOR_PASSWORD", "Vendedor2026@")
PASSWORD_POLICY_MESSAGE = (
    f"La contraseña debe tener al menos {PASSWORD_MIN_LENGTH} caracteres, incluir una letra mayúscula, una minúscula, "
    "un dígito y un símbolo."
)
BACKUP_DIR = resolve_backup_dir()
BACKUP_KEEP = max(1, int(os.environ.get("APP_BACKUP_KEEP", "10")))
BACKUP_SALES_LIMIT = max(100, int(os.environ.get("APP_BACKUP_SALES_LIMIT", "2000")))
BACKUP_MOVEMENTS_LIMIT = max(
    500, int(os.environ.get("APP_BACKUP_MOVEMENTS_LIMIT", "5000"))
)
_auto_backup_default = "0" if os.environ.get("PYTEST_CURRENT_TEST") else "1"
AUTO_BACKUP_ENABLED = os.environ.get("APP_AUTO_BACKUP", _auto_backup_default) == "1"
AUTO_BACKUP_INTERVAL_MINUTES = max(
    5, int(os.environ.get("APP_AUTO_BACKUP_INTERVAL", "120"))
)
PRODUCT_IMAGE_MAX_BYTES = max(
    80_000, int(os.environ.get("PRODUCT_IMAGE_MAX_BYTES", "900000"))
)
FRONTEND_ASSET_VERSION_TOKEN = "__ASSET_VERSION__"
BACKUP_LOCK = threading.Lock()
BACKUP_TIMER: Optional[threading.Timer] = None
SCHEMA_MIGRATIONS_LOCK = threading.Lock()
SCHEMA_MIGRATIONS_READY = False
LOGIN_ATTEMPT_LIMIT = max(3, int(os.environ.get("LOGIN_ATTEMPT_LIMIT", "5")))
LOGIN_ATTEMPT_WINDOW_SECONDS = max(
    60, int(os.environ.get("LOGIN_ATTEMPT_WINDOW_SECONDS", "900"))
)
LOGIN_LOCKOUT_SECONDS = max(
    60, int(os.environ.get("LOGIN_LOCKOUT_SECONDS", "900"))
)
LOGIN_ATTEMPT_LOCK = threading.Lock()
LOGIN_ATTEMPTS: Dict[str, List[datetime]] = {}
LOGIN_LOCKOUTS: Dict[str, datetime] = {}


def get_db_conn():
    return mysql_connect(**DB_CONFIG)


def to_bogota_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return None
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=BOGOTA_TZ)
    return value.astimezone(BOGOTA_TZ)


def bogota_isoformat(value: Any) -> Optional[str]:
    localized = to_bogota_datetime(value)
    return localized.isoformat() if localized else None


def bogota_now_naive() -> datetime:
    """Return current Bogota time without tzinfo for session tracking."""
    return datetime.now(BOGOTA_TZ).replace(tzinfo=None)


def parse_session_datetime(raw_value: Any) -> Optional[datetime]:
    if not raw_value:
        return None
    try:
        parsed = datetime.fromisoformat(str(raw_value))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is not None:
        return parsed.astimezone(BOGOTA_TZ).replace(tzinfo=None)
    return parsed


def find_existing_sales_csv(csv_path: str = "data/sales_data.csv") -> Optional[str]:
    candidate = Path(csv_path)
    project_root = Path(__file__).resolve().parents[1]
    lookup_paths: List[Path] = []
    if candidate.is_absolute():
        lookup_paths.append(candidate)
    else:
        lookup_paths.extend(
            [
                Path.cwd() / candidate,
                project_root / candidate,
                Path(__file__).resolve().parent / candidate,
            ]
        )
    for path in lookup_paths:
        if path.exists() and path.is_file():
            return str(path.resolve())
    return None


def ensure_backup_dir() -> None:
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR, exist_ok=True)


def get_frontend_dir() -> Path:
    return Path(__file__).resolve().parent / "frontend"


def get_frontend_asset_version() -> str:
    version_sources = [
        get_frontend_dir() / "index.html",
        get_frontend_dir() / "app.js",
        get_frontend_dir() / "style.css",
    ]
    timestamps = [
        path.stat().st_mtime_ns for path in version_sources if path.exists() and path.is_file()
    ]
    if not timestamps:
        return "dev"
    return f"{max(timestamps):x}"


def ensure_schema_migrations_table(cur) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version VARCHAR(64) PRIMARY KEY,
            name VARCHAR(128) NOT NULL,
            applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            details_json LONGTEXT NULL
        )
        """
    )


def list_applied_schema_migrations(cur) -> set[str]:
    ensure_schema_migrations_table(cur)
    cur.execute("SELECT version FROM schema_migrations")
    rows = cur.fetchall() or []
    applied: set[str] = set()
    for row in rows:
        if isinstance(row, dict):
            value = row.get("version")
        elif isinstance(row, (tuple, list)) and row:
            value = row[0]
        else:
            value = None
        if value:
            applied.add(str(value))
    return applied


def _run_core_schema_bootstrap(cur, conn) -> Dict[str, int]:
    ensure_users_table(cur)
    ensure_products_table(cur)
    ensure_sales_tables(cur)
    ensure_inventory_movements_table(cur)
    ensure_audit_events_table(cur)
    ensure_price_audit_table(cur)
    ensure_session_table(cur)
    ensure_ai_logs_table(cur)
    ensure_app_config_table(cur)
    ensure_recommendations_table(cur)
    ensure_roles_permissions_table(cur)
    ensure_default_role_definitions(conn)
    return {"tables_ready": 10}


def _run_sales_void_schema_migration(cur) -> Dict[str, int]:
    ensure_sales_tables(cur)
    return {"ventas_actualizadas": 1}


def apply_schema_migrations(conn) -> List[Dict[str, Any]]:
    cur = conn.cursor()
    applied_now: List[Dict[str, Any]] = []
    try:
        ensure_schema_migrations_table(cur)
        applied = list_applied_schema_migrations(cur)
        migrations = [
            (
                "20260319_core_tables",
                "Tablas base y configuracion",
                lambda: _run_core_schema_bootstrap(cur, conn),
            ),
            (
                "20260319_legacy_schema",
                "Columnas e indices legacy",
                lambda: migrate_legacy_schema(cur),
            ),
            (
                "20260319_foreign_keys",
                "Motores InnoDB y claves foraneas",
                lambda: migrate_foreign_keys(cur),
            ),
            (
                "20260404_sales_voiding",
                "Columnas para deshabilitacion controlada de ventas",
                lambda: _run_sales_void_schema_migration(cur),
            ),
            (
                "20260405_sales_actor_foreign_keys",
                "Claves foraneas para autorizacion y deshabilitacion de ventas",
                lambda: migrate_foreign_keys(cur),
            ),
        ]
        for version, name, runner in migrations:
            if version in applied:
                continue
            details = runner() or {}
            cur.execute(
                """
                INSERT INTO schema_migrations (version, name, details_json)
                VALUES (%s, %s, %s)
                """,
                (version, name, json.dumps(details, ensure_ascii=False)),
            )
            conn.commit()
            applied_now.append({"version": version, "name": name, "details": details})
        return applied_now
    finally:
        try:
            cur.close()
        except Exception:
            pass


def ensure_runtime_schema(conn: Optional[Any] = None, *, force: bool = False) -> bool:
    global SCHEMA_MIGRATIONS_READY
    if SCHEMA_MIGRATIONS_READY and not force:
        return True
    owns_connection = conn is None
    local_conn = conn
    try:
        if local_conn is None:
            local_conn = get_db_conn()
    except Exception as exc:
        print(f"[schema] no se pudo abrir conexion para migraciones: {exc}")
        return False
    with SCHEMA_MIGRATIONS_LOCK:
        if SCHEMA_MIGRATIONS_READY and not force:
            if owns_connection and local_conn:
                local_conn.close()
            return True
        try:
            apply_schema_migrations(local_conn)
            SCHEMA_MIGRATIONS_READY = True
            return True
        except Exception as exc:
            try:
                local_conn.rollback()
            except Exception:
                pass
            print(f"[schema] error aplicando migraciones: {exc}")
            return False
        finally:
            if owns_connection and local_conn:
                local_conn.close()


def get_request_client_ip() -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        first = str(forwarded).split(",")[0].strip()
        if first:
            return first
    return str(request.remote_addr or "local").strip() or "local"


def build_login_attempt_key(username: str, client_ip: str) -> str:
    return auth_guard_utils.build_login_attempt_key(username, client_ip)


def prune_login_throttle_state(now: Optional[datetime] = None) -> None:
    auth_guard_utils.prune_login_throttle_state(
        LOGIN_ATTEMPTS,
        LOGIN_LOCKOUTS,
        now=now,
        login_attempt_window_seconds=LOGIN_ATTEMPT_WINDOW_SECONDS,
    )


def get_login_throttle_seconds_left(username: str, client_ip: str) -> int:
    return auth_guard_utils.get_login_throttle_seconds_left(
        username,
        client_ip,
        login_attempt_lock=LOGIN_ATTEMPT_LOCK,
        login_lockouts=LOGIN_LOCKOUTS,
        build_login_attempt_key=build_login_attempt_key,
        prune_login_throttle_state=prune_login_throttle_state,
    )


def register_failed_login_attempt(username: str, client_ip: str) -> int:
    return auth_guard_utils.register_failed_login_attempt(
        username,
        client_ip,
        login_attempt_lock=LOGIN_ATTEMPT_LOCK,
        login_attempts=LOGIN_ATTEMPTS,
        login_lockouts=LOGIN_LOCKOUTS,
        build_login_attempt_key=build_login_attempt_key,
        prune_login_throttle_state=prune_login_throttle_state,
        login_attempt_limit=LOGIN_ATTEMPT_LIMIT,
        login_lockout_seconds=LOGIN_LOCKOUT_SECONDS,
    )


def clear_login_attempts(username: str, client_ip: str) -> None:
    auth_guard_utils.clear_login_attempts(
        username,
        client_ip,
        login_attempt_lock=LOGIN_ATTEMPT_LOCK,
        login_attempts=LOGIN_ATTEMPTS,
        login_lockouts=LOGIN_LOCKOUTS,
        build_login_attempt_key=build_login_attempt_key,
    )


def _coerce_decimal(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    return value


def _normalize_snapshot_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for row in rows:
        copy = {}
        for key, value in row.items():
            if isinstance(value, (datetime,)):
                copy[key] = value.isoformat()
            else:
                copy[key] = _coerce_decimal(value)
        normalized.append(copy)
    return normalized


def prune_old_backups() -> None:
    backup_file_utils.prune_old_backups(
        backup_dir=BACKUP_DIR,
        backup_keep=BACKUP_KEEP,
    )


def perform_backup(*, reason: str = "manual") -> Optional[str]:
    return backup_runtime_utils.perform_backup(
        reason=reason,
        ensure_backup_dir=ensure_backup_dir,
        backup_dir=BACKUP_DIR,
        bogota_tz=BOGOTA_TZ,
        get_db_conn=get_db_conn,
        normalize_snapshot_rows=_normalize_snapshot_rows,
        serialize_product_row=serialize_product_row,
        backup_sales_limit=BACKUP_SALES_LIMIT,
        coerce_decimal=_coerce_decimal,
        backup_movements_limit=BACKUP_MOVEMENTS_LIMIT,
        offline_cache=OFFLINE_CACHE,
        prune_old_backups=prune_old_backups,
    )


def load_backup_payload(snapshot_path: str) -> Dict[str, Any]:
    return backup_file_utils.load_backup_payload(snapshot_path)


def build_backup_pdf_file(payload: Dict[str, Any]) -> io.BytesIO:
    return backup_file_utils.build_backup_pdf_file(
        payload,
        pdf_safe_text=pdf_safe_text,
        format_currency=format_export_currency,
    )


def build_backup_artifacts(snapshot_path: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return backup_file_utils.build_backup_artifacts(
        snapshot_path,
        payload,
        backup_dir=BACKUP_DIR,
        load_backup_payload=load_backup_payload,
        build_backup_pdf_file=build_backup_pdf_file,
    )


def normalize_backup_filename(filename: Any) -> str:
    return backup_file_utils.normalize_backup_filename(filename)


def resolve_backup_artifact_path(filename: Any) -> str:
    normalized = normalize_backup_filename(filename)
    return backup_file_utils.resolve_backup_artifact_path(
        normalized,
        backup_dir=BACKUP_DIR,
    )


def list_backup_entries(*, limit: int = 50) -> List[Dict[str, Any]]:
    return backup_file_utils.list_backup_entries(
        limit=limit,
        backup_dir=BACKUP_DIR,
        ensure_backup_dir=ensure_backup_dir,
        load_backup_payload=load_backup_payload,
    )


def _coerce_backup_bool(value: Any, default: bool = True) -> bool:
    return backup_runtime_utils.coerce_backup_bool(value, default)


def restore_backup_snapshot(
    snapshot_path: str,
    *,
    actor_user_id: Optional[int] = None,
    actor_username: Optional[str] = None,
) -> Dict[str, Any]:
    return backup_runtime_utils.restore_backup_snapshot(
        snapshot_path,
        actor_user_id=actor_user_id,
        actor_username=actor_username,
        load_backup_payload=load_backup_payload,
        get_db_conn=get_db_conn,
        ensure_runtime_schema=ensure_runtime_schema,
        parse_product_image_data_url=parse_product_image_data_url,
        default_iva_percent=DEFAULT_IVA_PERCENT,
        coerce_backup_bool=_coerce_backup_bool,
        record_audit_event=record_audit_event,
        offline_cache=OFFLINE_CACHE,
        bogota_tz=BOGOTA_TZ,
    )


def load_latest_backup() -> Optional[str]:
    return backup_file_utils.load_latest_backup(
        backup_dir=BACKUP_DIR,
        ensure_backup_dir=ensure_backup_dir,
        offline_cache=OFFLINE_CACHE,
    )


def _schedule_next_backup(interval_minutes: int) -> None:
    global BACKUP_TIMER
    if not AUTO_BACKUP_ENABLED:
        return
    if BACKUP_TIMER:
        BACKUP_TIMER.cancel()

    def _runner() -> None:
        with BACKUP_LOCK:
            perform_backup(reason="auto")
        _schedule_next_backup(interval_minutes)

    BACKUP_TIMER = threading.Timer(interval_minutes * 60, _runner)
    BACKUP_TIMER.daemon = True
    BACKUP_TIMER.start()


def initialize_backup_scheduler() -> None:
    if not AUTO_BACKUP_ENABLED:
        return
    with BACKUP_LOCK:
        performed = perform_backup(reason="startup")
    if not performed and not OFFLINE_CACHE.has_snapshot():
        load_latest_backup()
    _schedule_next_backup(AUTO_BACKUP_INTERVAL_MINUTES)


def cancel_backup_scheduler() -> None:
    global BACKUP_TIMER
    if BACKUP_TIMER:
        BACKUP_TIMER.cancel()
        BACKUP_TIMER = None


load_latest_backup()


def hash_password(password: str) -> str:
    return hash_password_strict(password)


def enforce_password_policy(password: str) -> None:
    enforce_password_policy_strict(password)


def ensure_default_user(
    conn,
    username: str,
    password_plain: str,
    name: str,
    role: str,
    legacy_passwords: Optional[List[str]] = None,
) -> None:
    cur = conn.cursor(dictionary=True)
    try:
        ensure_users_table(cur)
        ensure_roles_permissions_table(cur)
        conn.commit()
        cur.execute("SELECT id, password FROM usuarios WHERE username=%s", (username,))
        row = cur.fetchone()
        enforce_password_policy(password_plain)
        new_hash = hash_password(password_plain)
        if not row:
            cur.execute(
                """
                INSERT INTO usuarios (username, password, name, role, activo)
                VALUES (%s, %s, %s, %s, 1)
                """,
                (username, new_hash, name, role),
            )
            conn.commit()
        else:
            current_hash = row.get("password")
            legacy_match = any(
                verify_password(candidate, current_hash)
                for candidate in (legacy_passwords or [])
                if candidate
            )
            if legacy_match or needs_password_rehash(current_hash):
                cur.execute(
                    "UPDATE usuarios SET password=%s WHERE id=%s", (new_hash, row["id"])
                )
                conn.commit()
    finally:
        cur.close()


def ensure_seed_users(conn) -> None:
    ensure_default_role_definitions(conn)
    ensure_default_user(
        conn,
        "admin",
        DEFAULT_ADMIN_PASSWORD,
        "Administrador",
        "admin",
        legacy_passwords=["admin123", "Admin123!"],
    )
    ensure_default_user(
        conn,
        "vendedor",
        DEFAULT_VENDOR_PASSWORD,
        "Vendedor Demo",
        "vendedor",
        legacy_passwords=["vendedor123", "Vendedor123!"],
    )


def reset_user_password(
    conn,
    username: str,
    password: str,
    *,
    role: str = "vendedor",
    name: Optional[str] = None,
    activate: bool = True,
) -> Dict[str, Any]:
    normalized_username = (username or "").strip().lower()
    if not normalized_username:
        raise ValueError("El usuario es obligatorio.")
    normalized_role = coerce_user_role(role or "vendedor")
    enforce_password_policy(password)
    hashed_password = hash_password(password)
    cur = conn.cursor(dictionary=True)
    try:
        ensure_users_table(cur)
        ensure_default_role_definitions(conn)
        role_def = fetch_role_definition(cur, normalized_role)
        if not role_def:
            save_role_definition(
                cur,
                role=normalized_role,
                name=role_display_name(normalized_role),
                permissions=default_role_permissions(normalized_role),
                is_system=False,
            )
            conn.commit()
        cur.execute(
            "SELECT id, username FROM usuarios WHERE username=%s LIMIT 1",
            (normalized_username,),
        )
        existing = cur.fetchone()
        display_name = (name or "").strip() or normalized_username
        active_value = 1 if activate else 0
        if existing and existing.get("id"):
            cur.execute(
                """
                UPDATE usuarios
                SET password=%s, name=%s, role=%s, activo=%s
                WHERE id=%s
                """,
                (
                    hashed_password,
                    display_name,
                    normalized_role,
                    active_value,
                    existing["id"],
                ),
            )
            conn.commit()
            return {
                "id": int(existing["id"]),
                "username": normalized_username,
                "created": False,
                "role": normalized_role,
            }
        cur.execute(
            """
            INSERT INTO usuarios (username, password, name, role, activo)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (normalized_username, hashed_password, display_name, normalized_role, active_value),
        )
        conn.commit()
        return {
            "id": int(cur.lastrowid or 0),
            "username": normalized_username,
            "created": True,
            "role": normalized_role,
        }
    finally:
        cur.close()


def unlock_admin_password(new_password: str) -> Tuple[bool, str]:
    raw_password = (new_password or "").strip()
    if not raw_password:
        return False, "Debes indicar una contraseña para admin."
    conn = None
    try:
        conn = get_db_conn()
        result = reset_user_password(
            conn,
            "admin",
            raw_password,
            role="admin",
            name="Administrador",
            activate=True,
        )
        return True, f"Admin desbloqueado. Usuario={result.get('username')} ID={result.get('id')}"
    except ValueError as exc:
        return False, str(exc)
    except Exception as exc:
        return False, f"No se pudo desbloquear admin: {exc}"
    finally:
        if conn:
            conn.close()


def coerce_decimal(
    value: Any,
    field: str,
    min_value: Decimal = PRICE_MIN,
    max_value: Optional[Decimal] = PRICE_MAX,
) -> Decimal:
    try:
        dec = parse_decimal(value)
    except ValueError as exc:
        raise ValueError(f"El campo '{field}' debe ser un numero valido.") from exc
    if dec < min_value:
        raise ValueError(f"El campo '{field}' debe ser mayor o igual a {min_value}.")
    if max_value is not None and dec > max_value:
        raise ValueError(
            f"El campo '{field}' supera el maximo permitido ({max_value})."
        )
    return dec


def coerce_int(
    value: Any,
    field: str,
    min_value: int = STOCK_MIN,
    max_value: Optional[int] = STOCK_MAX,
) -> int:
    try:
        intval = parse_int(value)
    except ValueError as exc:
        raise ValueError(
            f"El campo '{field}' debe ser un numero entero valido."
        ) from exc
    if intval < min_value:
        raise ValueError(f"El campo '{field}' debe ser mayor o igual a {min_value}.")
    if max_value is not None and intval > max_value:
        raise ValueError(
            f"El campo '{field}' supera el maximo permitido ({max_value})."
        )
    return intval


def normalize_price(dec: Decimal) -> Decimal:
    try:
        return dec.quantize(PRICE_STEP)
    except (InvalidOperation, TypeError):
        return dec


def normalize_iva(dec: Decimal) -> Decimal:
    try:
        return dec.quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError):
        return dec


def parse_product_image_data_url(
    value: Any,
) -> Tuple[Optional[bytes], Optional[str], bool]:
    """
    Devuelve (blob, mime, has_change):
    - has_change=False: no se solicitó cambio de imagen.
    - has_change=True y blob=None: limpiar imagen actual.
    - has_change=True y blob!=None: actualizar imagen.
    """
    if value is None:
        return None, None, False
    if not isinstance(value, str):
        raise ValueError("Formato de imagen inválido.")
    raw = value.strip()
    if raw == "":
        return None, None, True
    match = re.match(r"^data:(image/[a-zA-Z0-9.+-]+);base64,(.+)$", raw, re.DOTALL)
    if not match:
        raise ValueError("Formato de imagen inválido. Usa data URL base64.")
    mime = (match.group(1) or "").strip().lower()
    if mime not in {"image/jpeg", "image/png", "image/webp", "image/gif"}:
        raise ValueError("Formato de imagen no soportado. Usa JPG, PNG, WEBP o GIF.")
    b64_data = re.sub(r"\s+", "", match.group(2) or "")
    try:
        blob = base64.b64decode(b64_data, validate=True)
    except Exception as exc:
        raise ValueError("No se pudo decodificar la imagen enviada.") from exc
    if not blob:
        raise ValueError("La imagen está vacía.")
    if len(blob) > PRODUCT_IMAGE_MAX_BYTES:
        raise ValueError(
            f"La imagen supera el límite de {PRODUCT_IMAGE_MAX_BYTES // 1024} KB."
        )
    return blob, mime, True


def build_product_image_url(blob: Any, mime: Any) -> Optional[str]:
    if not blob:
        return None
    if isinstance(blob, str):
        # Puede venir ya base64 desde SQL (TO_BASE64)
        encoded = blob.strip().replace("\n", "").replace("\r", "")
    else:
        try:
            encoded = base64.b64encode(bytes(blob)).decode("ascii")
        except Exception:
            return None
    if not encoded:
        return None
    mime_value = str(mime or "image/jpeg").strip().lower() or "image/jpeg"
    return f"data:{mime_value};base64,{encoded}"


def serialize_product_row(row: Dict[str, Any]) -> Dict[str, Any]:
    payload = dict(row or {})
    image_url = payload.get("imagen_url")
    if not image_url:
        image_url = build_product_image_url(
            payload.get("imagen_blob") or payload.get("imagen_b64"),
            payload.get("imagen_mime"),
        )
    payload["imagen_url"] = image_url or ""
    payload.pop("imagen_blob", None)
    payload.pop("imagen_b64", None)
    try:
        payload["iva_percent"] = float(
            payload.get("iva_percent")
            if payload.get("iva_percent") is not None
            else DEFAULT_IVA_PERCENT
        )
    except Exception:
        payload["iva_percent"] = float(DEFAULT_IVA_PERCENT)
    try:
        price_base = float(
            payload.get("precio")
            if payload.get("precio") is not None
            else 0.0
        )
    except Exception:
        price_base = 0.0
    iva_value = round(price_base * payload["iva_percent"] / 100, 2)
    payload["precio"] = price_base
    payload["precio_base"] = price_base
    payload["iva_porcentaje"] = payload["iva_percent"]
    payload["iva_valor"] = iva_value
    payload["precio_con_iva"] = round(price_base + iva_value, 2)
    payload["image_url"] = payload["imagen_url"]
    if payload.get("activo") is None:
        payload["activo"] = 1
    return payload


def get_allowed_payment_methods_config() -> List[str]:
    return ["efectivo", "nequi", "daviplata", "transferencia"]


def ensure_app_config_table(cur) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS configuracion_app (
            config_key VARCHAR(64) PRIMARY KEY,
            config_value VARCHAR(255) NOT NULL,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        )
        """
    )


def get_app_config_value(cur, key: str, default: Optional[str] = None) -> Optional[str]:
    ensure_app_config_table(cur)
    cur.execute(
        "SELECT config_value FROM configuracion_app WHERE config_key=%s LIMIT 1",
        (key,),
    )
    row = cur.fetchone()
    if isinstance(row, dict):
        value = row.get("config_value")
        return str(value) if value is not None else default
    if row:
        try:
            return str(row[0]) if row[0] is not None else default
        except Exception:
            return default
    return default


def set_app_config_value(cur, key: str, value: Any) -> None:
    ensure_app_config_table(cur)
    cur.execute(
        """
        INSERT INTO configuracion_app (config_key, config_value)
        VALUES (%s, %s)
        ON DUPLICATE KEY UPDATE
            config_value=VALUES(config_value),
            updated_at=CURRENT_TIMESTAMP
        """,
        (key, str(value)),
    )


def build_iva_config_payload(cur) -> Dict[str, Any]:
    iva_percent = float(get_configured_iva_percent(cur))
    return {
        "iva_percent": iva_percent,
        "allowed_payment_methods": get_allowed_payment_methods_config(),
    }


def get_configured_iva_percent(cur) -> Decimal:
    raw_value = get_app_config_value(
        cur, "global_iva_percent", str(DEFAULT_IVA_PERCENT)
    )
    try:
        return normalize_iva(
            coerce_decimal(raw_value, "iva_percent", IVA_MIN, IVA_MAX)
        )
    except ValueError:
        return normalize_iva(DEFAULT_IVA_PERCENT)


def validate_product_payload(data: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("Datos invalidos para el producto.")
    errors: List[str] = []
    nombre = (data.get("nombre") or "").strip()
    if not nombre:
        errors.append("El nombre del producto es obligatorio.")
    categoria = (data.get("categoria") or "").strip()
    if not categoria:
        errors.append("La categoria del producto es obligatoria.")
    precio = stock = min_stock = iva_percent = None
    try:
        precio = normalize_price(coerce_decimal(data.get("precio"), "precio"))
    except ValueError as exc:
        errors.append(str(exc))
    try:
        stock = coerce_int(data.get("stock"), "stock")
    except ValueError as exc:
        errors.append(str(exc))
    try:
        min_stock = coerce_int(data.get("min_stock"), "min_stock")
    except ValueError as exc:
        errors.append(str(exc))
    try:
        iva_input = data.get("iva_percent")
        if iva_input is None or str(iva_input).strip() == "":
            iva_percent = normalize_iva(DEFAULT_IVA_PERCENT)
        else:
            iva_percent = normalize_iva(
                coerce_decimal(iva_input, "iva_percent", IVA_MIN, IVA_MAX)
            )
    except ValueError as exc:
        errors.append(str(exc))
    if errors:
        raise ValueError(" ".join(errors))
    return {
        "nombre": nombre,
        "categoria": categoria,
        "precio": float(precio) if precio is not None else None,
        "iva_percent": float(iva_percent) if iva_percent is not None else None,
        "stock": stock,
        "min_stock": min_stock,
    }


def safe_get(data: Any, key: str, default: Any = None) -> Any:
    return data.get(key, default) if isinstance(data, dict) else default


def calculate_price_change_ratio(
    old_price: Optional[float], new_price: Optional[float]
) -> float:
    if old_price is None or old_price <= 0:
        return float("inf") if (new_price or 0) > 0 else 0.0
    if new_price is None:
        return 0.0
    try:
        old_val = float(old_price)
        new_val = float(new_price)
        diff = abs(new_val - old_val)
        return diff / old_val if old_val else float("inf")
    except (TypeError, ValueError):
        return float("inf")


def ensure_price_audit_table(cur) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS producto_precio_auditoria (
            id INT AUTO_INCREMENT PRIMARY KEY,
            producto_id INT NOT NULL,
            usuario_id INT,
            precio_anterior DECIMAL(12,2),
            precio_nuevo DECIMAL(12,2),
            motivo TEXT,
            creado_en TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def record_price_change(
    conn,
    producto_id: int,
    usuario_id: Optional[int],
    old_price: float,
    new_price: float,
    reason: Optional[str],
) -> None:
    cur = conn.cursor()
    ensure_price_audit_table(cur)
    cur.execute(
        """
        INSERT INTO producto_precio_auditoria (producto_id, usuario_id, precio_anterior, precio_nuevo, motivo)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (
            producto_id,
            usuario_id,
            old_price,
            new_price,
            reason[:255] if reason else None,
        ),
    )
    conn.commit()
    cur.close()


def record_inventory_movement(
    cur,
    *,
    producto_id: int,
    tipo: str,
    cantidad: int,
    stock_anterior: int,
    stock_nuevo: int,
    motivo: str,
    usuario_id: Optional[int],
) -> int:
    ensure_inventory_movements_table(cur)
    cur.execute(
        """
        INSERT INTO inventario_movimientos (
            producto_id, tipo, cantidad, stock_anterior, stock_nuevo, motivo, usuario_id
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (
            int(producto_id),
            (tipo or "ajuste").strip().lower(),
            int(cantidad),
            int(stock_anterior),
            int(stock_nuevo),
            (motivo or "").strip()[:255],
            usuario_id,
        ),
    )
    return int(cur.lastrowid or 0)


def record_audit_event(
    cur,
    *,
    event_type: str,
    entity_type: str,
    entity_id: Optional[int],
    description: str,
    details: Optional[Dict[str, Any]] = None,
    actor_user_id: Optional[int] = None,
    actor_username: Optional[str] = None,
) -> int:
    ensure_audit_events_table(cur)
    payload = json.dumps(details or {}, ensure_ascii=False)
    cur.execute(
        """
        INSERT INTO auditoria_eventos (
            event_type, entity_type, entity_id, description, details_json, actor_user_id, actor_username
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (
            (event_type or "").strip().lower()[:64],
            (entity_type or "").strip().lower()[:32],
            entity_id,
            (description or "").strip()[:255] or "Evento registrado",
            payload,
            actor_user_id,
            (actor_username or "").strip()[:64] or None,
        ),
    )
    return int(cur.lastrowid or 0)


def try_record_audit_event(
    conn,
    *,
    event_type: str,
    entity_type: str,
    entity_id: Optional[int],
    description: str,
    details: Optional[Dict[str, Any]] = None,
    actor_user_id: Optional[int] = None,
    actor_username: Optional[str] = None,
) -> None:
    if conn is None:
        return
    cur = None
    try:
        cur = conn.cursor()
        record_audit_event(
            cur,
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            description=description,
            details=details,
            actor_user_id=actor_user_id,
            actor_username=actor_username,
        )
        conn.commit()
    except Exception as exc:
        try:
            conn.rollback()
        except Exception:
            pass
        print(f"[audit] no se pudo registrar evento `{event_type}`: {exc}")
    finally:
        if cur:
            try:
                cur.close()
            except Exception:
                pass


def ensure_users_table(cur) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS usuarios (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(64) NOT NULL UNIQUE,
            password VARCHAR(128) NOT NULL,
            name VARCHAR(128),
            role VARCHAR(32) DEFAULT 'vendedor',
            activo TINYINT(1) NOT NULL DEFAULT 1,
            creado_en TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def ensure_products_table(cur) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS productos (
            id INT AUTO_INCREMENT PRIMARY KEY,
            nombre VARCHAR(128) NOT NULL,
            categoria VARCHAR(128),
            precio DECIMAL(12,2) NOT NULL DEFAULT 0.00,
            iva_percent DECIMAL(5,2) NOT NULL DEFAULT 19.00,
            stock INT NOT NULL DEFAULT 0,
            min_stock INT NOT NULL DEFAULT 0,
            activo TINYINT(1) NOT NULL DEFAULT 1,
            imagen_blob LONGBLOB NULL,
            imagen_mime VARCHAR(64) NULL,
            creado_en TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    try:
        cur.execute(
            "ALTER TABLE productos ADD COLUMN iva_percent DECIMAL(5,2) NOT NULL DEFAULT 19.00"
        )
    except Exception:
        pass
    try:
        cur.execute(
            "ALTER TABLE productos ADD COLUMN activo TINYINT(1) NOT NULL DEFAULT 1"
        )
    except Exception:
        pass
    try:
        cur.execute("ALTER TABLE productos ADD COLUMN imagen_blob LONGBLOB NULL")
    except Exception:
        pass
    try:
        cur.execute("ALTER TABLE productos ADD COLUMN imagen_mime VARCHAR(64) NULL")
    except Exception:
        pass


def ensure_sales_tables(cur) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS ventas (
            id INT AUTO_INCREMENT PRIMARY KEY,
            fecha DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            usuario_id INT,
            metodo_pago VARCHAR(32),
            total DECIMAL(12,2) NOT NULL DEFAULT 0.00,
            anulada TINYINT(1) NOT NULL DEFAULT 0,
            anulada_en DATETIME NULL,
            anulada_por INT NULL,
            anulacion_motivo VARCHAR(255) NULL,
            anulacion_autorizada TINYINT(1) NOT NULL DEFAULT 0,
            anulacion_autorizada_en DATETIME NULL,
            anulacion_autorizada_por INT NULL,
            INDEX idx_fecha (fecha)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS venta_detalle (
            id INT AUTO_INCREMENT PRIMARY KEY,
            venta_id INT NOT NULL,
            producto_id INT NOT NULL,
            cantidad INT NOT NULL,
            precio DECIMAL(12,2) NOT NULL,
            iva_percent DECIMAL(5,2) NOT NULL DEFAULT 0.00,
            INDEX idx_venta (venta_id),
            INDEX idx_producto (producto_id)
        )
        """
    )
    try:
        cur.execute(
            "ALTER TABLE ventas ADD COLUMN iva_percent DECIMAL(5,2) NOT NULL DEFAULT 0.00"
        )
    except Exception:
        pass
    try:
        cur.execute(
            "ALTER TABLE ventas ADD COLUMN anulada TINYINT(1) NOT NULL DEFAULT 0"
        )
    except Exception:
        pass
    try:
        cur.execute("ALTER TABLE ventas ADD COLUMN anulada_en DATETIME NULL")
    except Exception:
        pass
    try:
        cur.execute("ALTER TABLE ventas ADD COLUMN anulada_por INT NULL")
    except Exception:
        pass
    try:
        cur.execute(
            "ALTER TABLE ventas ADD COLUMN anulacion_motivo VARCHAR(255) NULL"
        )
    except Exception:
        pass
    try:
        cur.execute(
            "ALTER TABLE ventas ADD COLUMN anulacion_autorizada TINYINT(1) NOT NULL DEFAULT 0"
        )
    except Exception:
        pass
    try:
        cur.execute(
            "ALTER TABLE ventas ADD COLUMN anulacion_autorizada_en DATETIME NULL"
        )
    except Exception:
        pass
    try:
        cur.execute(
            "ALTER TABLE ventas ADD COLUMN anulacion_autorizada_por INT NULL"
        )
    except Exception:
        pass
    try:
        cur.execute(
            "ALTER TABLE venta_detalle ADD COLUMN iva_percent DECIMAL(5,2) NOT NULL DEFAULT 0.00"
        )
    except Exception:
        pass


def ensure_inventory_movements_table(cur) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS inventario_movimientos (
            id INT AUTO_INCREMENT PRIMARY KEY,
            producto_id INT NOT NULL,
            tipo VARCHAR(16) NOT NULL,
            cantidad INT NOT NULL,
            stock_anterior INT NOT NULL,
            stock_nuevo INT NOT NULL,
            motivo VARCHAR(255),
            usuario_id INT NULL,
            creado_en TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_inv_producto (producto_id),
            INDEX idx_inv_fecha (creado_en)
        )
        """
    )


def ensure_audit_events_table(cur) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS auditoria_eventos (
            id INT AUTO_INCREMENT PRIMARY KEY,
            event_type VARCHAR(64) NOT NULL,
            entity_type VARCHAR(32) NOT NULL,
            entity_id INT NULL,
            description VARCHAR(255) NOT NULL,
            details_json LONGTEXT NULL,
            actor_user_id INT NULL,
            actor_username VARCHAR(64) NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_audit_created (created_at),
            INDEX idx_audit_event_type (event_type),
            INDEX idx_audit_entity (entity_type, entity_id)
        )
        """
    )


def ensure_session_table(cur) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS sesiones_activas (
            token VARCHAR(128) PRIMARY KEY,
            user_id INT NOT NULL,
            role VARCHAR(32),
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_activity TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            revoked TINYINT(1) NOT NULL DEFAULT 0,
            client_info VARCHAR(255)
        )
        """
    )


def ensure_ai_logs_table(cur) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS tabla_logs_ia (
            id INT AUTO_INCREMENT PRIMARY KEY,
            fecha_ejecucion DATETIME NOT NULL,
            payload_json LONGTEXT NOT NULL,
            fuente VARCHAR(64),
            version VARCHAR(32),
            creado_en TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_fecha_ejecucion (fecha_ejecucion)
        )
        """
    )


def perform_sessions_cleanup(conn: Optional[Any] = None) -> Dict[str, int]:
    return session_core_utils.perform_sessions_cleanup(
        get_db_conn=get_db_conn,
        ensure_session_table=ensure_session_table,
        conn=conn,
    )


def bootstrap_database() -> Dict[str, int]:
    conn = get_db_conn()
    stats: Dict[str, int] = {}
    cur = None
    try:
        apply_schema_migrations(conn)
        ensure_seed_users(conn)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM usuarios")
        stats["usuarios"] = int(cur.fetchone()[0])
        cur.execute("SELECT COUNT(*) FROM productos")
        stats["productos"] = int(cur.fetchone()[0])
        cur.execute("SELECT COUNT(*) FROM ventas")
        stats["ventas"] = int(cur.fetchone()[0])
        cur.execute("SELECT COUNT(*) FROM schema_migrations")
        stats["migraciones"] = int(cur.fetchone()[0])
        return stats
    finally:
        if cur:
            try:
                cur.close()
            except Exception:
                pass
        conn.close()


def get_session_state(
    token: Optional[str], idle_minutes: Optional[int] = None, refresh: bool = False
) -> SessionState:
    return session_core_utils.get_session_state(
        token,
        get_db_conn=get_db_conn,
        ensure_session_table=ensure_session_table,
        idle_minutes=idle_minutes,
        refresh=refresh,
    )


def store_session_token(
    conn,
    token: str,
    user_id: int,
    role: str,
    idle_minutes: int,
    client_info: Optional[str] = None,
) -> None:
    session_core_utils.store_session_token(
        conn,
        token,
        user_id,
        role,
        idle_minutes,
        ensure_session_table=ensure_session_table,
        client_info=client_info,
    )


def update_session_activity(token: Optional[str], idle_minutes: int) -> bool:
    return session_core_utils.update_session_activity(
        token,
        idle_minutes,
        get_session_state_fn=get_session_state,
    )


def revoke_session_token(token: Optional[str]) -> None:
    session_core_utils.revoke_session_token(
        token,
        get_db_conn=get_db_conn,
        ensure_session_table=ensure_session_table,
    )


def serialize_session_record(
    row: Dict[str, Any], current_token: Optional[str]
) -> Dict[str, Any]:
    return session_core_utils.serialize_session_record(
        row,
        current_token,
        bogota_isoformat=bogota_isoformat,
    )


@app.route("/api/sesiones", methods=["GET"])
def api_sessions_list():
    permission_check = require_permission("sessions_manage")
    if permission_check:
        return permission_check
    conn = get_db_conn()
    try:
        cur = conn.cursor(dictionary=True)
        ensure_session_table(cur)
        cleanup_expired_sessions(cur, conn)
        cur.execute(
            """
            SELECT s.token, s.user_id, s.role, s.created_at, s.last_activity, s.expires_at, s.revoked, s.client_info,
                   u.username, u.name
            FROM sesiones_activas s
            LEFT JOIN usuarios u ON u.id = s.user_id
            ORDER BY s.revoked ASC, s.last_activity DESC
            """
        )
        rows = cur.fetchall() or []
        current_token = session.get("session_token")
        sessions_payload = [
            serialize_session_record(row, current_token) for row in rows
        ]
        active_count = sum(1 for item in sessions_payload if item["status"] == "active")
        return jsonify(
            {
                "sessions": sessions_payload,
                "summary": {"total": len(sessions_payload), "active": active_count},
            }
        )
    finally:
        conn.close()


@app.route("/api/sesiones/<token>", methods=["DELETE"])
def api_admin_session_revoke(token: str):
    permission_check = require_permission("sessions_manage")
    if permission_check:
        return permission_check
    token = (token or "").strip()
    if not token:
        return jsonify({"success": False, "error": "Token requerido"}), 400
    conn = get_db_conn()
    revoked = False
    try:
        cur = conn.cursor()
        ensure_session_table(cur)
        cur.execute("UPDATE sesiones_activas SET revoked=1 WHERE token=%s", (token,))
        conn.commit()
        revoked = cur.rowcount > 0
    finally:
        conn.close()
    current_revoked = revoked and token == session.get("session_token")
    if current_revoked:
        session.clear()
    return jsonify(
        {
            "success": True,
            "revoked": revoked,
            "current_session_revoked": current_revoked,
        }
    )


@app.route("/api/sesiones/limpiar", methods=["POST"])
def api_sessions_cleanup():
    permission_check = require_permission("sessions_manage")
    if permission_check:
        return permission_check
    stats = perform_sessions_cleanup()
    return jsonify({"success": True, "revoked": stats["revoked"]})


def ensure_recommendations_table(cur) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS venta_recomendaciones (
            id INT AUTO_INCREMENT PRIMARY KEY,
            venta_id INT NOT NULL,
            combos JSON,
            restock JSON,
            canal VARCHAR(32),
            estado VARCHAR(32) DEFAULT 'pendiente',
            creado_en TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            notificado_en TIMESTAMP NULL,
            UNIQUE KEY (venta_id)
        )
        """
    )


def store_sale_recommendations(
    cur,
    venta_id: int,
    combos: List[Dict[str, Any]],
    restock: List[Dict[str, Any]],
    canal: str = "console",
    estado: str = "pendiente",
) -> None:
    ensure_recommendations_table(cur)
    cur.execute(
        """
        INSERT INTO venta_recomendaciones (venta_id, combos, restock, canal, estado)
        VALUES (%s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE combos=VALUES(combos), restock=VALUES(restock), canal=VALUES(canal), estado=VALUES(estado), creado_en=CURRENT_TIMESTAMP
        """,
        (
            venta_id,
            json.dumps(combos, ensure_ascii=False),
            json.dumps(restock, ensure_ascii=False),
            canal,
            estado,
        ),
    )


def get_idle_timeout_for_role(role: Optional[str]) -> int:
    return session_core_utils.get_idle_timeout_for_role(
        role,
        role_idle_timeouts=ROLE_IDLE_TIMEOUTS,
        default_idle_timeout=SESSION_IDLE_TIMEOUT_MINUTES,
    )


def apply_role_session_defaults(user: Dict[str, Any]) -> None:
    idle_minutes = get_idle_timeout_for_role(user.get("role"))
    session["idle_minutes"] = idle_minutes
    session["max_idle_seconds"] = idle_minutes * 60


def is_session_bound_to_current_boot() -> bool:
    return auth_guard_utils.is_session_bound_to_current_boot(
        session,
        server_boot_id=SERVER_BOOT_ID,
        testing_enabled=bool(app.config.get("TESTING")),
    )


def revoke_and_clear_session() -> None:
    auth_guard_utils.revoke_and_clear_session(
        session,
        revoke_session_token=revoke_session_token,
    )


def check_login() -> bool:
    return auth_guard_utils.check_login(
        session,
        is_session_bound_to_current_boot=is_session_bound_to_current_boot,
    )


def require_login():
    return auth_guard_utils.require_login(
        session,
        check_login=check_login,
        jsonify=jsonify,
    )


def require_admin():
    return auth_guard_utils.require_admin(
        session,
        check_login=check_login,
        jsonify=jsonify,
    )


def get_session_permissions() -> Dict[str, bool]:
    return auth_guard_utils.get_session_permissions(
        session,
        coerce_user_role=coerce_user_role,
        normalize_permissions_map=normalize_permissions_map,
    )


def require_permission(permission_key: str):
    return auth_guard_utils.require_permission(
        permission_key,
        session_store=session,
        require_login=require_login,
        get_session_permissions=get_session_permissions,
        jsonify=jsonify,
    )


def generate_session_token() -> str:
    return session_core_utils.generate_session_token()


def should_skip_session_enforcement(endpoint: str) -> bool:
    return auth_flow_utils.should_skip_session_enforcement(endpoint)


def describe_session_failure(state: SessionState) -> Tuple[str, str]:
    return auth_flow_utils.describe_session_failure(
        state,
        revoked_message="Sesion revocada por un administrador",
        expired_message="Sesion expirada",
    )


def read_session_idle_status() -> Tuple[datetime, int, bool]:
    return auth_flow_utils.read_session_idle_status(
        session,
        bogota_now_naive=bogota_now_naive,
        parse_session_datetime=parse_session_datetime,
        default_idle_minutes=SESSION_IDLE_TIMEOUT_MINUTES,
    )


def refresh_active_session(state: SessionState, *, now_local: datetime) -> None:
    auth_flow_utils.refresh_active_session(
        session,
        state,
        now_local=now_local,
        sync_session_expiration_fields=sync_session_expiration_fields,
    )


def process_login_request(payload: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    return auth_flow_utils.process_login_request(
        payload,
        get_request_client_ip=get_request_client_ip,
        get_login_throttle_seconds_left=get_login_throttle_seconds_left,
        get_db_conn=get_db_conn,
        ensure_runtime_schema=ensure_runtime_schema,
        ensure_seed_users=ensure_seed_users,
        fetch_user_by_credentials=fetch_user_by_credentials,
        register_failed_login_attempt=register_failed_login_attempt,
        clear_login_attempts=clear_login_attempts,
        build_user_payload=build_user_payload,
        finalize_login_session=finalize_login_session,
        try_record_audit_event=try_record_audit_event,
        print_fn=print,
    )


@app.before_request
def enforce_session_timeout():
    endpoint = request.endpoint or ""
    if should_skip_session_enforcement(endpoint):
        return
    if "user_id" in session and not is_session_bound_to_current_boot():
        revoke_and_clear_session()
    if not check_login():
        return
    now_local, idle_minutes, idle_expired = read_session_idle_status()
    if idle_expired:
        revoke_and_clear_session()
        if request.path.startswith("/api/"):
            return jsonify({"error": "Sesion expirada", "reason": "expired"}), 401
        return redirect("/")
    token = session.get("session_token")
    state = get_session_state(token, idle_minutes=idle_minutes, refresh=True)
    if not state.ok:
        reason_key, error_message = describe_session_failure(state)
        revoke_and_clear_session()
        if request.path.startswith("/api/"):
            return jsonify({"error": error_message, "reason": reason_key}), 401
        return redirect("/")
    refresh_active_session(state, now_local=now_local)


def fetch_user_by_credentials(
    conn, username: str, password: str
) -> Optional[Dict[str, Any]]:
    cur = conn.cursor(dictionary=True)
    try:
        ensure_users_table(cur)
        conn.commit()
        cur.execute(
            """
            SELECT
                u.id,
                u.username,
                u.name,
                u.role,
                u.password,
                u.activo,
                rp.name AS role_name,
                rp.permissions_json
            FROM usuarios u
            LEFT JOIN roles_permisos rp ON rp.role = u.role
            WHERE u.username=%s
            """,
            (username,),
        )
        row = cur.fetchone()
        if not row or not row.get("activo"):
            return None
        stored_hash = row.get("password")
        if not verify_password(password, stored_hash):
            return None
        if needs_password_rehash(stored_hash):
            try:
                cur.execute(
                    "UPDATE usuarios SET password=%s WHERE id=%s",
                    (hash_password(password), row.get("id")),
                )
                conn.commit()
            except Exception as exc:
                print(f"[auth] no se pudo actualizar hash de contraseña: {exc}")
        return row
    finally:
        cur.close()


def build_user_payload(row: Dict[str, Any]) -> Dict[str, Any]:
    role = coerce_user_role((row or {}).get("role") or "vendedor")
    permissions_raw: Any = None
    if isinstance(row, dict):
        permissions_raw = row.get("permissions")
        if permissions_raw is None and row.get("permissions_json"):
            try:
                permissions_raw = json.loads(row.get("permissions_json") or "{}")
            except Exception:
                permissions_raw = {}
    permissions = normalize_permissions_map(permissions_raw or {}, role=role)
    return {
        "id": row.get("id"),
        "username": row.get("username"),
        "name": row.get("name") or row.get("username"),
        "role": role,
        "role_name": (row.get("role_name") or "").strip() or role_display_name(role),
        "permissions": permissions,
    }


def build_session_user_payload() -> Dict[str, Any]:
    return auth_session_utils.build_session_user_payload(
        session,
        role_display_name=role_display_name,
        normalize_permissions_map=normalize_permissions_map,
        default_idle_minutes=SESSION_IDLE_TIMEOUT_MINUTES,
        warning_seconds=SESSION_WARNING_SECONDS,
        price_change_max_ratio=PRICE_CHANGE_MAX_RATIO,
        price_force_reason_min_length=PRICE_FORCE_REASON_MIN_LENGTH,
    )


def sync_session_expiration_fields(state: SessionState) -> None:
    auth_session_utils.sync_session_expiration_fields(
        session,
        state,
        bogota_isoformat=bogota_isoformat,
    )


def finalize_login_session(conn, user_payload: Dict[str, Any]) -> Dict[str, Any]:
    return auth_session_utils.finalize_login_session(
        conn,
        user_payload,
        session_store=session,
        server_boot_id=SERVER_BOOT_ID,
        bogota_now_naive=bogota_now_naive,
        normalize_permissions_map=normalize_permissions_map,
        role_display_name=role_display_name,
        apply_role_session_defaults=apply_role_session_defaults,
        generate_session_token=generate_session_token,
        store_session_token=store_session_token,
        get_session_state=get_session_state,
        sync_session_expiration_fields=sync_session_expiration_fields,
        build_session_user_payload=build_session_user_payload,
        warning_seconds=SESSION_WARNING_SECONDS,
        user_agent=request.headers.get("User-Agent"),
    )


def build_session_status_payload(state: SessionState) -> Dict[str, Any]:
    return auth_session_utils.build_session_status_payload(
        session,
        state,
        parse_session_datetime=parse_session_datetime,
        bogota_now_naive=bogota_now_naive,
        bogota_isoformat=bogota_isoformat,
        default_idle_minutes=SESSION_IDLE_TIMEOUT_MINUTES,
        warning_seconds=SESSION_WARNING_SECONDS,
    )


def build_session_ping_response(state: SessionState) -> Dict[str, Any]:
    return auth_session_utils.build_session_ping_response(
        session,
        state,
        bogota_now_naive=bogota_now_naive,
        sync_session_expiration_fields=sync_session_expiration_fields,
    )


@app.route("/api/login", methods=["POST"])
def api_login():
    """
    Iniciar sesion de usuario
    ---
    tags:
      - Autenticacion
    consumes:
      - application/json
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - username
            - password
          properties:
            username:
              type: string
            password:
              type: string
    responses:
      200:
        description: Autenticacion exitosa
      400:
        description: Datos incompletos
      401:
        description: Credenciales invalidas
    """
    payload = request.get_json(force=True) or {}
    response_payload, status_code = process_login_request(payload)
    return jsonify(response_payload), status_code


@app.route("/api/logout", methods=["POST"])
def api_logout():
    username = session.get("username")
    user_id = session.get("user_id")
    token = session.get("session_token")
    try:
        conn = get_db_conn()
    except Exception:
        conn = None
    try:
        try_record_audit_event(
            conn,
            event_type="logout",
            entity_type="sesion",
            entity_id=user_id,
            description=f'Cierre de sesión para "{username or "desconocido"}"',
            details={"client_ip": get_request_client_ip()},
            actor_user_id=user_id,
            actor_username=username,
        )
    finally:
        if conn:
            conn.close()
    revoke_session_token(token)
    session.clear()
    return jsonify({"success": True})


@app.route("/api/current_user", methods=["GET"])
def api_current_user():
    """
    Obtener informacion del usuario autenticado
    ---
    tags:
      - Autenticacion
    responses:
      200:
        description: Sesion activa
      401:
        description: Sesion no valida
    """
    if not check_login():
        return jsonify({"user": None})
    return jsonify({"user": build_session_user_payload()})


@app.route("/api/session/status", methods=["GET"])
def api_session_status():
    """
    Consultar estado de la sesion actual
    ---
    tags:
      - Sesiones
    responses:
      200:
        description: Sesion activa
      401:
        description: Sesion no valida
    """
    if not check_login():
        return (
            jsonify(
                {
                    "active": False,
                    "seconds_left": 0,
                    "warning_seconds": SESSION_WARNING_SECONDS,
                    "reason": "unauthenticated",
                }
            ),
            401,
        )
    token = session.get("session_token")
    state = get_session_state(token)
    if not state.ok:
        reason_key, message = describe_session_failure(state)
        if state.revoked:
            message = f"{message}."
        else:
            message = f"{message}."
        session.clear()
        return (
            jsonify(
                {
                    "active": False,
                    "seconds_left": 0,
                    "warning_seconds": SESSION_WARNING_SECONDS,
                    "reason": reason_key,
                    "message": message,
                }
            ),
            401,
        )
    return jsonify(build_session_status_payload(state))


@app.route("/api/session/ping", methods=["POST"])
def api_session_ping():
    """
    Renovar la sesion activa
    ---
    tags:
      - Sesiones
    responses:
      200:
        description: Sesion renovada
      401:
        description: Sesion invalida
    """
    if not check_login():
        return jsonify({"success": False, "error": "No autenticado"}), 401
    idle_minutes = session.get("idle_minutes", SESSION_IDLE_TIMEOUT_MINUTES)
    state = get_session_state(
        session.get("session_token"), idle_minutes=idle_minutes, refresh=True
    )
    if not state.ok:
        reason_key, message = describe_session_failure(state)
        message = f"{message}."
        session.clear()
        return jsonify({"success": False, "error": message, "reason": reason_key}), 401
    return jsonify(build_session_ping_response(state))


@app.route("/healthz", methods=["GET"])
def healthcheck():
    return (
        jsonify(
            {
                "ok": True,
                "service": "la_septima_estrella",
                "db_online": bool(mysql_ping(DB_CONFIG, timeout=2)),
            }
        ),
        200,
    )


@app.route("/api/system/status", methods=["GET"])
def api_system_status():
    if not check_login():
        return jsonify({"error": "No autenticado"}), 401
    status = OFFLINE_CACHE.status()
    status.update(
        {
            "backup_dir": BACKUP_DIR,
            "auto_backup_enabled": AUTO_BACKUP_ENABLED,
            "auto_backup_interval_minutes": AUTO_BACKUP_INTERVAL_MINUTES,
        }
    )
    return jsonify(status)


@app.route("/api/backups/manual", methods=["POST"])
def api_backup_manual():
    permission_check = require_permission("backups_manage")
    if permission_check:
        return permission_check
    with BACKUP_LOCK:
        path = perform_backup(reason="manual-api")
    if not path:
        return (
            jsonify({"success": False, "error": "No se pudo generar el respaldo."}),
            500,
        )
    artifacts = build_backup_artifacts(path)
    try:
        conn = get_db_conn()
    except Exception:
        conn = None
    try:
        try_record_audit_event(
            conn,
            event_type="respaldo_generado",
            entity_type="sistema",
            entity_id=None,
            description=f'Respaldo manual generado: "{artifacts["json_filename"]}"',
            details={
                "json_filename": artifacts["json_filename"],
                "pdf_filename": artifacts["pdf_filename"],
            },
            actor_user_id=session.get("user_id"),
            actor_username=session.get("username"),
        )
    finally:
        if conn:
            conn.close()
    return jsonify(
        {
            "success": True,
            "path": path,
            "created_at": datetime.now(BOGOTA_TZ).isoformat(),
            **artifacts,
        }
    )


@app.route("/api/backups", methods=["GET"])
def api_backups_list():
    permission_check = require_permission("backups_manage")
    if permission_check:
        return permission_check
    try:
        limit = max(1, min(int(request.args.get("limit", "30")), 100))
    except (TypeError, ValueError):
        limit = 30
    return jsonify({"success": True, "items": list_backup_entries(limit=limit)})


@app.route("/api/backups/download/<path:filename>", methods=["GET"])
def api_backups_download(filename: str):
    permission_check = require_permission("backups_manage")
    if permission_check:
        return permission_check
    try:
        artifact_path = resolve_backup_artifact_path(filename)
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except FileNotFoundError:
        return jsonify({"success": False, "error": "Respaldo no encontrado."}), 404
    return send_file(artifact_path, as_attachment=True, download_name=os.path.basename(artifact_path))


@app.route("/api/backups/restore", methods=["POST"])
def api_backups_restore():
    permission_check = require_permission("backups_manage")
    if permission_check:
        return permission_check
    payload = request.get_json(force=True) or {}
    filename = payload.get("filename") or payload.get("json_filename")
    if not filename:
        return jsonify({"success": False, "error": "Indica el archivo JSON a restaurar."}), 400
    try:
        artifact_path = resolve_backup_artifact_path(filename)
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except FileNotFoundError:
        return jsonify({"success": False, "error": "Respaldo no encontrado."}), 404
    if not artifact_path.lower().endswith(".json"):
        return jsonify({"success": False, "error": "La restauración solo acepta snapshots JSON."}), 400
    try:
        result = restore_backup_snapshot(
            artifact_path,
            actor_user_id=session.get("user_id"),
            actor_username=session.get("username"),
        )
        return jsonify(result)
    except Exception as exc:
        print(f"[backup] error restaurando respaldo `{filename}`: {exc}")
        return jsonify({"success": False, "error": "No se pudo restaurar el respaldo."}), 500


@app.route("/api/session/revoke", methods=["POST"])
def api_session_revoke():
    """
    Revocar una sesion activa
    ---
    tags:
      - Sesiones
    consumes:
      - application/json
    parameters:
      - in: body
        name: body
        schema:
          type: object
          required:
            - token
          properties:
            token:
              type: string
    responses:
      200:
        description: Sesion revocada
      400:
        description: Token faltante
      403:
        description: Requiere rol administrador
    """
    admin_check = require_admin()
    if admin_check:
        return admin_check
    payload = request.get_json(force=True) or {}
    token = (payload.get("token") or "").strip()
    if not token:
        return jsonify({"success": False, "error": "Token requerido"}), 400
    revoke_session_token(token)
    return jsonify({"success": True})


@app.route("/api/config/iva", methods=["GET", "PUT"])
def api_config_iva():
    if request.method == "GET":
        permission_check = require_permission("products_view")
    else:
        permission_check = require_permission("products_manage")
    if permission_check:
        return permission_check
    conn = get_db_conn()
    try:
        cur = conn.cursor(dictionary=True)
        ensure_app_config_table(cur)
        if request.method == "GET":
            conn.commit()
            return jsonify(build_iva_config_payload(cur))
        data = request.get_json(force=True) or {}
        try:
            iva_percent = normalize_iva(
                coerce_decimal(data.get("iva_percent"), "iva_percent", IVA_MIN, IVA_MAX)
            )
        except ValueError as exc:
            return jsonify({"success": False, "error": str(exc)}), 400
        previous_iva = float(get_configured_iva_percent(cur))
        set_app_config_value(cur, "global_iva_percent", iva_percent)
        try:
            record_audit_event(
                cur,
                event_type="configuracion_iva_actualizada",
                entity_type="configuracion",
                entity_id=None,
                description="IVA global actualizado",
                details={
                    "iva_percent": {
                        "before": previous_iva,
                        "after": float(iva_percent),
                    }
                },
                actor_user_id=session.get("user_id"),
                actor_username=session.get("username"),
            )
        except Exception as exc:
            print(f"[audit] no se pudo registrar cambio de IVA: {exc}")
        conn.commit()
        payload = build_iva_config_payload(cur)
        payload["success"] = True
        return jsonify(payload)
    finally:
        conn.close()


@app.route("/api/roles", methods=["GET", "POST"])
def api_roles():
    permission_check = require_permission("users_manage")
    if permission_check:
        return permission_check
    conn = get_db_conn()
    try:
        cur = conn.cursor(dictionary=True)
        ensure_default_role_definitions(conn)
        ensure_roles_permissions_table(cur)
        if request.method == "GET":
            cur.execute(
                """
                SELECT role, name, permissions_json, is_system
                FROM roles_permisos
                ORDER BY is_system DESC, role ASC
                """
            )
            rows = cur.fetchall() or []
            roles = []
            for row in rows:
                if not row or not row.get("role"):
                    continue
                try:
                    permissions_raw = json.loads(row.get("permissions_json") or "{}")
                except (TypeError, ValueError, json.JSONDecodeError):
                    permissions_raw = {}
                roles.append(
                    {
                        "role": coerce_user_role(row.get("role")),
                        "name": (row.get("name") or "").strip()
                        or role_display_name(row.get("role")),
                        "permissions": normalize_permissions_map(
                            permissions_raw, role=row.get("role")
                        ),
                        "is_system": bool(row.get("is_system")),
                    }
                )
            return jsonify(
                {
                    "roles": roles,
                    "permission_labels": ROLE_PERMISSION_LABELS,
                }
            )
        data = request.get_json(force=True) or {}
        try:
            role = normalize_user_role(data.get("role") or "")
        except ValueError as exc:
            return jsonify({"success": False, "error": str(exc)}), 400
        role_name = (data.get("name") or role_display_name(role)).strip()
        permissions = normalize_permissions_map(data.get("permissions") or {}, role=role)
        if not any(permissions.values()):
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Selecciona al menos un permiso para el rol.",
                    }
                ),
                400,
            )
        existing = fetch_role_definition(cur, role)
        if existing:
            return jsonify({"success": False, "error": "El rol ya existe."}), 409
        save_role_definition(
            cur,
            role=role,
            name=role_name,
            permissions=permissions,
            is_system=False,
        )
        try:
            record_audit_event(
                cur,
                event_type="rol_creado",
                entity_type="rol",
                entity_id=None,
                description=f'Rol "{role}" creado',
                details={"role": role, "name": role_name, "permissions": permissions},
                actor_user_id=session.get("user_id"),
                actor_username=session.get("username"),
            )
        except Exception as exc:
            print(f"[audit] no se pudo registrar creación de rol: {exc}")
        conn.commit()
        created = fetch_role_definition(cur, role) or {
            "role": role,
            "name": role_name or role_display_name(role),
            "permissions": permissions,
            "is_system": False,
        }
        created["success"] = True
        return jsonify(created), 201
    finally:
        conn.close()


@app.route("/api/usuarios", methods=["GET", "POST"])
def api_usuarios():
    """
    Administrar usuarios
    ---
    get:
      tags: [Usuarios]
      responses:
        200:
          description: Lista de usuarios
        403:
          description: Se requiere rol administrador
    post:
      tags: [Usuarios]
      consumes:
        - application/json
      parameters:
        - in: body
          name: body
          schema:
            type: object
            required: [username, password, role]
            properties:
              username:
                type: string
              password:
                type: string
              name:
                type: string
              role:
                type: string
      responses:
        200:
          description: Usuario creado
        400:
          description: Datos invalidos
        403:
          description: Se requiere rol administrador
    """
    permission_check = require_permission("users_manage")
    if permission_check:
        return permission_check
    conn = get_db_conn()
    try:
        cur = conn.cursor(dictionary=True)
        ensure_users_table(cur)
        ensure_default_role_definitions(conn)
        conn.commit()
        if request.method == "GET":
            cur.execute("SELECT id, username, name, role, activo FROM usuarios ORDER BY id")
            rows = cur.fetchall() or []
            return jsonify([build_user_payload(row) | {"activo": bool(row.get("activo", 1))} for row in rows])
        data = request.get_json(force=True) or {}
        username = (data.get("username") or "").strip()
        role = coerce_user_role((data.get("role") or "vendedor").strip())
        raw_password = (data.get("password") or "").strip()
        if not username:
            return jsonify({"success": False, "error": "Falta el usuario"}), 400
        if not raw_password:
            return (
                jsonify({"success": False, "error": "La contraseña es obligatoria."}),
                400,
            )
        try:
            enforce_password_policy(raw_password)
        except ValueError as exc:
            return jsonify({"success": False, "error": str(exc)}), 400
        if not role_exists(cur, role):
            return jsonify({"success": False, "error": "El rol indicado no existe."}), 400
        cur.execute(
            """
            INSERT INTO usuarios (username, password, name, role, activo)
            VALUES (%s, %s, %s, %s, 1)
            """,
            (username, hash_password(raw_password), data.get("name", ""), role),
        )
        user_id = int(cur.lastrowid or 0)
        record_audit_event(
            cur,
            event_type="usuario_creado",
            entity_type="usuario",
            entity_id=user_id,
            description=f'Usuario "{username}" creado',
            details={
                "username": username,
                "name": (data.get("name") or "").strip() or username,
                "role": role,
                "activo": True,
            },
            actor_user_id=session.get("user_id"),
            actor_username=session.get("username"),
        )
        conn.commit()
        return jsonify({"success": True, "id": user_id})
    finally:
        conn.close()


@app.route("/api/usuarios/<int:uid>", methods=["GET", "PUT", "DELETE"])
def api_usuario(uid: int):
    """
    Operaciones sobre un usuario
    ---
    get:
      tags: [Usuarios]
      parameters:
        - in: path
          name: uid
          required: true
          type: integer
      responses:
        200:
          description: Usuario encontrado
        404:
          description: Usuario no existe
    put:
      tags: [Usuarios]
      consumes:
        - application/json
      parameters:
        - in: path
          name: uid
          required: true
          type: integer
        - in: body
          name: body
          schema:
            type: object
            properties:
              username: {type: string}
              password: {type: string}
              name: {type: string}
              role: {type: string}
      responses:
        200:
          description: Usuario actualizado
        400:
          description: Datos invalidos
    delete:
      tags: [Usuarios]
      parameters:
        - in: path
          name: uid
          required: true
          type: integer
      responses:
        200:
          description: Usuario eliminado
    """
    permission_check = require_permission("users_manage")
    if permission_check:
        return permission_check
    conn = get_db_conn()
    try:
        cur = conn.cursor(dictionary=True)
        ensure_users_table(cur)
        ensure_default_role_definitions(conn)
        conn.commit()
        if request.method == "GET":
            cur.execute(
                "SELECT id, username, name, role, activo FROM usuarios WHERE id=%s",
                (uid,),
            )
            user = cur.fetchone()
            if not user:
                return jsonify({"error": "Usuario no encontrado"}), 404
            payload = build_user_payload(user)
            payload["activo"] = bool(user.get("activo", 1))
            return jsonify(payload)
        cur.execute(
            "SELECT id, username, name, role, activo FROM usuarios WHERE id=%s",
            (uid,),
        )
        current_user = cur.fetchone()
        if not current_user:
            return jsonify({"error": "Usuario no encontrado"}), 404
        if request.method == "DELETE":
            target_role = coerce_user_role(current_user.get("role") or "vendedor")
            if target_role == "admin" and session.get("role") != "admin":
                return jsonify({"error": "Solo admin puede desactivar otro admin."}), 403
            if target_role == "admin" and bool(current_user.get("activo", 1)):
                active_admins = count_active_admins(cur)
                if active_admins <= 1:
                    return jsonify({"error": "Debe existir al menos un admin activo."}), 409
            cur.execute("UPDATE usuarios SET activo=0 WHERE id=%s", (uid,))
            record_audit_event(
                cur,
                event_type="usuario_eliminado",
                entity_type="usuario",
                entity_id=uid,
                description=f'Usuario "{current_user.get("username")}" desactivado',
                details={
                    "activo": {"before": bool(current_user.get("activo", 1)), "after": False},
                    "role": current_user.get("role"),
                },
                actor_user_id=session.get("user_id"),
                actor_username=session.get("username"),
            )
            conn.commit()
            return jsonify({"success": True})
        data = request.get_json(force=True) or {}
        fields: List[str] = []
        params: List[Any] = []
        audit_details: Dict[str, Any] = {}
        if "username" in data:
            fields.append("username=%s")
            params.append(data["username"])
            audit_details["username"] = {
                "before": current_user.get("username"),
                "after": data["username"],
            }
        if "name" in data:
            fields.append("name=%s")
            params.append(data["name"])
            audit_details["name"] = {
                "before": current_user.get("name"),
                "after": data["name"],
            }
        if "role" in data:
            normalized_role = coerce_user_role(data["role"])
            if not role_exists(cur, normalized_role):
                return jsonify({"success": False, "error": "El rol indicado no existe."}), 400
            fields.append("role=%s")
            params.append(normalized_role)
            audit_details["role"] = {
                "before": current_user.get("role"),
                "after": normalized_role,
            }
        if "password" in data:
            raw_password = (data.get("password") or "").strip()
            if not raw_password:
                return (
                    jsonify(
                        {"success": False, "error": "La contraseña es obligatoria."}
                    ),
                    400,
                )
            try:
                enforce_password_policy(raw_password)
            except ValueError as exc:
                return jsonify({"success": False, "error": str(exc)}), 400
            fields.append("password=%s")
            params.append(hash_password(raw_password))
            audit_details["password"] = {"before": "oculta", "after": "actualizada"}
        if fields:
            sql = f"UPDATE usuarios SET {', '.join(fields)} WHERE id=%s"
            params.append(uid)
            cur.execute(sql, params)
            record_audit_event(
                cur,
                event_type="usuario_actualizado",
                entity_type="usuario",
                entity_id=uid,
                description=f'Usuario "{current_user.get("username")}" actualizado',
                details=audit_details,
                actor_user_id=session.get("user_id"),
                actor_username=session.get("username"),
            )
            conn.commit()
        return jsonify({"success": True})
    finally:
        conn.close()


@app.route("/api/usuarios/<int:uid>/estado", methods=["PUT"])
def api_usuario_estado(uid: int):
    """
    Activar o desactivar un usuario
    ---
    tags: [Usuarios]
    consumes:
      - application/json
    parameters:
      - in: path
        name: uid
        required: true
        type: integer
      - in: body
        name: body
        schema:
          type: object
          required:
            - activo
          properties:
            activo:
              type: boolean
    responses:
      200:
        description: Estado actualizado
      403:
        description: Requiere rol administrador
    """
    permission_check = require_permission("users_manage")
    if permission_check:
        return permission_check
    data = request.get_json(force=True) or {}
    activo = 1 if data.get("activo") else 0
    conn = get_db_conn()
    try:
        cur = conn.cursor(dictionary=True)
        ensure_users_table(cur)
        conn.commit()
        cur.execute("SELECT id, role, activo FROM usuarios WHERE id=%s", (uid,))
        row = cur.fetchone()
        if not row:
            return jsonify({"success": False, "error": "Usuario no encontrado"}), 404
        target_role = coerce_user_role(row.get("role") or "vendedor")
        if target_role == "admin" and session.get("role") != "admin":
            return jsonify({"success": False, "error": "Solo admin puede modificar otro admin."}), 403
        if target_role == "admin" and int(row.get("activo") or 0) == 1 and activo == 0:
            if count_active_admins(cur) <= 1:
                return (
                    jsonify(
                        {
                            "success": False,
                            "error": "Debe existir al menos un administrador activo.",
                        }
                    ),
                    409,
                )
        cur.execute("UPDATE usuarios SET activo=%s WHERE id=%s", (activo, uid))
        record_audit_event(
            cur,
            event_type="usuario_estado_actualizado",
            entity_type="usuario",
            entity_id=uid,
            description=f"Estado actualizado para usuario #{uid}",
            details={
                "activo": {
                    "before": bool(row.get("activo", 1)),
                    "after": bool(activo),
                }
            },
            actor_user_id=session.get("user_id"),
            actor_username=session.get("username"),
        )
        conn.commit()
        return jsonify({"success": True})
    finally:
        conn.close()


@app.route("/api/productos/<int:pid>/estado", methods=["PUT"])
def api_producto_estado(pid: int):
    permission_check = require_permission("products_manage")
    if permission_check:
        return permission_check
    data = request.get_json(force=True) or {}
    activo = 1 if data.get("activo") else 0
    conn = get_db_conn()
    try:
        current = fetch_product(conn, pid)
        if not current:
            return jsonify({"success": False, "error": "Producto no encontrado"}), 404
        cur = conn.cursor()
        cur.execute("UPDATE productos SET activo=%s WHERE id=%s", (activo, pid))
        record_audit_event(
            cur,
            event_type="producto_estado_actualizado",
            entity_type="producto",
            entity_id=pid,
            description=f'Estado actualizado para producto "{current.get("nombre")}"',
            details={
                "activo": {
                    "before": bool(current.get("activo", 1)),
                    "after": bool(activo),
                }
            },
            actor_user_id=session.get("user_id"),
            actor_username=session.get("username"),
        )
        conn.commit()
        return jsonify({"success": True})
    finally:
        conn.close()


def fetch_product(conn, product_id: int) -> Optional[Dict[str, Any]]:
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute(
            """
            SELECT
                id,
                nombre,
                categoria,
                precio,
                iva_percent,
                stock,
                min_stock,
                activo,
                imagen_mime,
                REPLACE(TO_BASE64(imagen_blob), '\n', '') AS imagen_b64,
                creado_en
            FROM productos
            WHERE id=%s
            """,
            (product_id,),
        )
        row = cur.fetchone()
        return serialize_product_row(row) if row else None
    finally:
        cur.close()


def fetch_exportable_products(conn) -> List[Dict[str, Any]]:
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute(
            """
            SELECT
                id,
                nombre,
                categoria,
                precio,
                iva_percent,
                stock,
                min_stock,
                activo,
                imagen_mime,
                REPLACE(TO_BASE64(imagen_blob), '\n', '') AS imagen_b64,
                creado_en
            FROM productos
            ORDER BY nombre ASC
            """
        )
        rows = cur.fetchall() or []
        payload: List[Dict[str, Any]] = []
        for row in rows:
            serialized = serialize_product_row(row)
            payload.append(
                {
                    "id": serialized.get("id"),
                    "nombre": serialized.get("nombre"),
                    "categoria": serialized.get("categoria"),
                    "precio": serialized.get("precio_base"),
                    "iva_percent": serialized.get("iva_percent"),
                    "stock": serialized.get("stock"),
                    "min_stock": serialized.get("min_stock"),
                    "activo": 1 if serialized.get("activo") else 0,
                    "imagen_data_url": serialized.get("imagen_url") or "",
                    "creado_en": serialized.get("creado_en"),
                }
            )
        return payload
    finally:
        cur.close()


def normalize_inventory_file_format(raw_value: Optional[str]) -> str:
    value = (raw_value or "csv").strip().lower()
    if value in {"csv", "excel", "pdf"}:
        return value
    raise ValueError("Formato de inventario invalido. Usa pdf, csv o excel.")


def build_inventory_export_file(
    rows: List[Dict[str, Any]], export_format: str
) -> Tuple[io.BytesIO, str, str]:
    ordered_columns = [
        "id",
        "nombre",
        "categoria",
        "precio",
        "iva_percent",
        "stock",
        "min_stock",
        "activo",
        "imagen_data_url",
        "creado_en",
    ]
    if export_format == "excel":
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Inventario"
        sheet.append(ordered_columns)
        for row in rows:
            sheet.append([row.get(column) for column in ordered_columns])
        output = io.BytesIO()
        workbook.save(output)
        output.seek(0)
        return (
            output,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "xlsx",
        )
    if export_format == "pdf":
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()
        line_width = pdf.w - pdf.l_margin - pdf.r_margin
        pdf.set_font("Helvetica", "B", 16)
        pdf.cell(
            0,
            10,
            pdf_safe_text("Inventario de productos"),
            new_x="LMARGIN",
            new_y="NEXT",
        )
        pdf.set_font("Helvetica", size=10)
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(
            line_width,
            6,
            pdf_safe_text(f"Productos exportados: {len(rows)}"),
        )
        pdf.ln(2)
        pdf.set_font("Helvetica", size=9)
        if not rows:
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(
                line_width,
                6,
                pdf_safe_text("No hay productos disponibles para exportar."),
            )
        for row in rows:
            state = "Activo" if int(row.get("activo") or 0) else "Inactivo"
            line = (
                f"{row.get('nombre') or '-'} | "
                f"{row.get('categoria') or '-'} | "
                f"Precio: {format_export_currency(row.get('precio'))} | "
                f"IVA: {row.get('iva_percent') or 0}% | "
                f"Stock: {int(row.get('stock') or 0)} | "
                f"Min: {int(row.get('min_stock') or 0)} | "
                f"{state}"
            )
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(line_width, 6, pdf_safe_text(line))
        output = io.BytesIO(bytes(pdf.output()))
        output.seek(0)
        return output, "application/pdf", "pdf"
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=ordered_columns)
    writer.writeheader()
    for row in rows:
        writer.writerow({column: row.get(column) for column in ordered_columns})
    encoded = io.BytesIO(output.getvalue().encode("utf-8-sig"))
    encoded.seek(0)
    return encoded, "text/csv; charset=utf-8", "csv"


INVENTORY_IMPORT_COLUMN_ALIASES = {
    "id": {"id", "producto_id"},
    "nombre": {"nombre", "producto", "name"},
    "categoria": {"categoria", "categoria_producto", "category"},
    "precio": {"precio", "precio_base", "price"},
    "iva_percent": {"iva_percent", "iva", "iva_porcentaje", "iva_producto"},
    "stock": {"stock", "existencias", "inventario"},
    "min_stock": {"min_stock", "stock_minimo", "minimo", "minimo_stock"},
    "activo": {"activo", "estado", "habilitado"},
    "imagen_data_url": {"imagen_data_url", "imagen_url", "image_url", "imagen"},
}


def _resolve_import_column_map(columns: List[str]) -> Dict[str, str]:
    normalized_columns = {
        normalize_lookup_text(column): str(column) for column in columns if column is not None
    }
    resolved: Dict[str, str] = {}
    for target, aliases in INVENTORY_IMPORT_COLUMN_ALIASES.items():
        for alias in aliases:
            matched = normalized_columns.get(normalize_lookup_text(alias))
            if matched:
                resolved[target] = matched
                break
    return resolved


def _coerce_import_active(value: Any) -> bool:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return True
    if isinstance(value, bool):
        return value
    raw = str(value).strip().lower()
    if raw in {"", "1", "true", "si", "sí", "yes", "activo", "activa"}:
        return True
    if raw in {"0", "false", "no", "inactivo", "inactiva"}:
        return False
    return True


def load_inventory_import_rows(file_storage, default_iva: Decimal) -> List[Dict[str, Any]]:
    filename = str(getattr(file_storage, "filename", "") or "").strip()
    if not filename:
        raise ValueError("Selecciona un archivo CSV o Excel.")
    ext = os.path.splitext(filename.lower())[1]
    raw_bytes = file_storage.read()
    if not raw_bytes:
        raise ValueError("El archivo de inventario está vacío.")
    buffer = io.BytesIO(raw_bytes)
    if ext == ".csv":
        try:
            text = raw_bytes.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw_bytes.decode("latin-1")
        frame = pd.read_csv(io.StringIO(text))
    elif ext in {".xlsx", ".xls"}:
        frame = pd.read_excel(buffer)
    else:
        raise ValueError("Formato no soportado. Usa CSV o Excel (.xlsx).")
    if frame.empty:
        raise ValueError("El archivo no contiene filas de inventario.")
    frame = frame.where(pd.notna(frame), None)
    column_map = _resolve_import_column_map(list(frame.columns))
    required = {"nombre", "precio", "stock", "min_stock"}
    missing = sorted(required - set(column_map))
    if missing:
        raise ValueError(
            "Faltan columnas requeridas: " + ", ".join(missing) + "."
        )
    rows: List[Dict[str, Any]] = []
    errors: List[str] = []
    for index, source_row in enumerate(frame.to_dict(orient="records"), start=2):
        raw: Dict[str, Any] = {}
        for target, source_column in column_map.items():
            raw[target] = source_row.get(source_column)
        payload = {
            "nombre": raw.get("nombre"),
            "categoria": raw.get("categoria") or "",
            "precio": raw.get("precio"),
            "iva_percent": raw.get("iva_percent")
            if raw.get("iva_percent") is not None
            else default_iva,
            "stock": raw.get("stock"),
            "min_stock": raw.get("min_stock"),
        }
        try:
            validated = validate_product_payload(payload)
            image_blob, image_mime, image_changed = parse_product_image_data_url(
                raw.get("imagen_data_url")
            )
            validated.update(
                {
                    "_source_line": index,
                    "_raw_id": raw.get("id"),
                    "activo": 1 if _coerce_import_active(raw.get("activo")) else 0,
                    "imagen_blob": image_blob,
                    "imagen_mime": image_mime,
                    "imagen_changed": image_changed,
                }
            )
            rows.append(validated)
        except ValueError as exc:
            errors.append(f"Fila {index}: {exc}")
    if errors:
        raise ValueError(" | ".join(errors[:8]))
    return rows


def apply_inventory_import(
    conn,
    rows: List[Dict[str, Any]],
    *,
    actor_user_id: Optional[int] = None,
    actor_username: Optional[str] = None,
    source_name: str = "",
) -> Dict[str, Any]:
    cur = conn.cursor(dictionary=True)
    conn.start_transaction()
    try:
        cur.execute(
            """
            SELECT id, nombre
            FROM productos
            """
        )
        existing_rows = cur.fetchall() or []
        by_id = {int(item.get("id") or 0): item for item in existing_rows if item.get("id")}
        by_name = {
            normalize_lookup_text(item.get("nombre")): item
            for item in existing_rows
            if item.get("nombre")
        }
        summary = {"created": 0, "updated": 0, "processed": len(rows)}
        for row in rows:
            candidate_id = row.get("_raw_id")
            matched = None
            if candidate_id not in (None, ""):
                try:
                    matched = by_id.get(int(candidate_id))
                except (TypeError, ValueError):
                    matched = None
            if not matched:
                matched = by_name.get(normalize_lookup_text(row.get("nombre")))
            if matched:
                if row.get("imagen_changed"):
                    cur.execute(
                        """
                        UPDATE productos
                        SET nombre=%s, categoria=%s, precio=%s, iva_percent=%s, stock=%s, min_stock=%s, activo=%s, imagen_blob=%s, imagen_mime=%s
                        WHERE id=%s
                        """,
                        (
                            row["nombre"],
                            row["categoria"],
                            row["precio"],
                            row["iva_percent"],
                            row["stock"],
                            row["min_stock"],
                            row["activo"],
                            row["imagen_blob"],
                            row["imagen_mime"],
                            matched["id"],
                        ),
                    )
                else:
                    cur.execute(
                        """
                        UPDATE productos
                        SET nombre=%s, categoria=%s, precio=%s, iva_percent=%s, stock=%s, min_stock=%s, activo=%s
                        WHERE id=%s
                        """,
                        (
                            row["nombre"],
                            row["categoria"],
                            row["precio"],
                            row["iva_percent"],
                            row["stock"],
                            row["min_stock"],
                            row["activo"],
                            matched["id"],
                        ),
                    )
                summary["updated"] += 1
                by_name[normalize_lookup_text(row.get("nombre"))] = {"id": matched["id"], "nombre": row.get("nombre")}
                continue
            cur.execute(
                """
                INSERT INTO productos (
                    nombre, categoria, precio, iva_percent, stock, min_stock, activo, imagen_blob, imagen_mime
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    row["nombre"],
                    row["categoria"],
                    row["precio"],
                    row["iva_percent"],
                    row["stock"],
                    row["min_stock"],
                    row["activo"],
                    row["imagen_blob"],
                    row["imagen_mime"],
                ),
            )
            new_id = int(cur.lastrowid or 0)
            summary["created"] += 1
            by_id[new_id] = {"id": new_id, "nombre": row.get("nombre")}
            by_name[normalize_lookup_text(row.get("nombre"))] = {"id": new_id, "nombre": row.get("nombre")}
        record_audit_event(
            cur,
            event_type="inventario_importado",
            entity_type="sistema",
            entity_id=None,
            description="Importación masiva de inventario completada",
            details={
                "source_name": source_name,
                "created": summary["created"],
                "updated": summary["updated"],
                "processed": summary["processed"],
            },
            actor_user_id=actor_user_id,
            actor_username=actor_username,
        )
        conn.commit()
        return summary
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


@app.route("/api/productos", methods=["GET", "POST"])
def api_productos():
    """
    Administrar productos
    ---
    get:
      tags: [Productos]
      parameters:
        - in: query
          name: search
          type: string
          required: false
          description: Filtro por nombre o categoria
      responses:
        200:
          description: Lista de productos
    post:
      tags: [Productos]
      consumes:
        - application/json
      parameters:
        - in: body
          name: body
          schema:
            type: object
            required: [nombre, categoria, precio, stock, min_stock]
            properties:
              nombre: {type: string}
              categoria: {type: string}
              precio: {type: number}
              stock: {type: integer}
              min_stock: {type: integer}
      responses:
        200:
          description: Producto creado
        400:
          description: Datos invalidos
        403:
          description: Requiere rol administrador
    """
    if request.method == "GET":
        permission_check = require_permission("products_view")
        if permission_check:
            return permission_check
        search = request.args.get("search", "").strip()
        try:
            conn = get_db_conn()
        except Exception as exc:
            print(f"[productos] no hay conexion a BD: {exc}")
            OFFLINE_CACHE.mark_offline(str(exc))
            fallback = OFFLINE_CACHE.get_products(search)
            if fallback:
                data = [enrich_product_with_alert(row) for row in fallback]
                response = jsonify(data)
                response.headers["X-Data-Source"] = "offline-cache"
                return response
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Inventario no disponible y no hay respaldo offline.",
                    }
                ),
                503,
            )
        try:
            cur = conn.cursor(dictionary=True)
            if search:
                like = f"%{search}%"
                cur.execute(
                    """
                    SELECT
                        id,
                        nombre,
                        categoria,
                        precio,
                        iva_percent,
                        stock,
                        min_stock,
                        activo,
                        imagen_mime,
                        REPLACE(TO_BASE64(imagen_blob), '\n', '') AS imagen_b64,
                        creado_en
                    FROM productos
                    WHERE nombre LIKE %s OR categoria LIKE %s
                    ORDER BY nombre
                    """,
                    (like, like),
                )
            else:
                cur.execute(
                    """
                    SELECT
                        id,
                        nombre,
                        categoria,
                        precio,
                        iva_percent,
                        stock,
                        min_stock,
                        activo,
                        imagen_mime,
                        REPLACE(TO_BASE64(imagen_blob), '\n', '') AS imagen_b64,
                        creado_en
                    FROM productos
                    ORDER BY nombre
                    """
                )
            rows = [serialize_product_row(row) for row in (cur.fetchall() or [])]
            OFFLINE_CACHE.mark_online()
            return jsonify([enrich_product_with_alert(row) for row in rows])
        except Exception as exc:
            print(f"[productos] error consultando inventario: {exc}")
            OFFLINE_CACHE.mark_offline(str(exc))
            fallback = OFFLINE_CACHE.get_products(search)
            if fallback:
                data = [enrich_product_with_alert(row) for row in fallback]
                response = jsonify(data)
                response.headers["X-Data-Source"] = "offline-cache"
                return response
            return (
                jsonify({"success": False, "error": "No se pudo consultar productos."}),
                500,
            )
        finally:
            conn.close()

    permission_check = require_permission("products_manage")
    if permission_check:
        return permission_check
    data = request.get_json(force=True) or {}
    try:
        product = validate_product_payload(data)
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    try:
        image_blob, image_mime, _ = parse_product_image_data_url(
            data.get("imagen_data_url")
        )
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    conn = get_db_conn()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            INSERT INTO productos (
                nombre, categoria, precio, iva_percent, stock, min_stock, activo, imagen_blob, imagen_mime
            )
            VALUES (%s, %s, %s, %s, %s, %s, 1, %s, %s)
            """,
            (
                product["nombre"],
                product["categoria"],
                product["precio"],
                product["iva_percent"],
                product["stock"],
                product["min_stock"],
                image_blob,
                image_mime,
            ),
        )
        product_id = int(cur.lastrowid or 0)
        record_audit_event(
            cur,
            event_type="producto_creado",
            entity_type="producto",
            entity_id=product_id,
            description=f'Producto "{product["nombre"]}" creado',
            details={"payload": product},
            actor_user_id=session.get("user_id"),
            actor_username=session.get("username"),
        )
        conn.commit()
        return jsonify({"success": True, "id": product_id})
    finally:
        conn.close()


@app.route("/api/productos/export", methods=["GET"])
def api_productos_export():
    permission_check = require_permission("products_view")
    if permission_check:
        return permission_check
    try:
        export_format = normalize_inventory_file_format(request.args.get("format"))
        conn = get_db_conn()
        ensure_runtime_schema(conn)
        rows = fetch_exportable_products(conn)
        output, mimetype, extension = build_inventory_export_file(rows, export_format)
        try_record_audit_event(
            conn,
            event_type="inventario_exportado",
            entity_type="sistema",
            entity_id=None,
            description="Exportación de inventario generada",
            details={"format": export_format, "total_productos": len(rows)},
            actor_user_id=session.get("user_id"),
            actor_username=session.get("username"),
        )
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        print(f"[productos] error exportando inventario: {exc}")
        return jsonify({"success": False, "error": "No se pudo exportar el inventario."}), 500
    finally:
        if "conn" in locals() and conn:
            conn.close()
    return send_file(
        output,
        mimetype=mimetype,
        as_attachment=True,
        download_name=f"inventario-productos.{extension}",
    )


@app.route("/api/productos/import", methods=["POST"])
def api_productos_import():
    permission_check = require_permission("products_manage")
    if permission_check:
        return permission_check
    file_storage = request.files.get("file")
    if not file_storage:
        return jsonify({"success": False, "error": "Adjunta un archivo CSV o Excel."}), 400
    conn = None
    try:
        conn = get_db_conn()
        ensure_runtime_schema(conn)
        cur = conn.cursor(dictionary=True)
        current_iva = get_configured_iva_percent(cur)
        cur.close()
        rows = load_inventory_import_rows(file_storage, current_iva)
        summary = apply_inventory_import(
            conn,
            rows,
            actor_user_id=session.get("user_id"),
            actor_username=session.get("username"),
            source_name=str(file_storage.filename or "").strip(),
        )
        return jsonify({"success": True, **summary})
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        print(f"[productos] error importando inventario: {exc}")
        return jsonify({"success": False, "error": "No se pudo importar el inventario."}), 500
    finally:
        if conn:
            conn.close()


@app.route("/api/productos/<int:pid>", methods=["GET", "PUT", "DELETE"])
def api_producto(pid: int):
    """
    Operaciones sobre un producto
    ---
    get:
      tags: [Productos]
      parameters:
        - in: path
          name: pid
          required: true
          type: integer
      responses:
        200:
          description: Producto obtenido
        404:
          description: Producto no encontrado
    put:
      tags: [Productos]
      consumes:
        - application/json
      parameters:
        - in: path
          name: pid
          required: true
          type: integer
        - in: body
          name: body
          schema:
            type: object
            properties:
              nombre: {type: string}
              categoria: {type: string}
              precio: {type: number}
              stock: {type: integer}
              min_stock: {type: integer}
              force: {type: boolean}
              force_reason: {type: string}
      responses:
        200:
          description: Producto actualizado
        400:
          description: Datos invalidos
        403:
          description: Requiere rol administrador
        404:
          description: Producto no encontrado
    delete:
      tags: [Productos]
      parameters:
        - in: path
          name: pid
          required: true
          type: integer
      responses:
        200:
          description: Producto eliminado
        403:
          description: Requiere rol administrador
    """
    permission_key = "products_view" if request.method == "GET" else "products_manage"
    permission_check = require_permission(permission_key)
    if permission_check:
        return permission_check
    try:
        conn = get_db_conn()
    except Exception as exc:
        print(f"[productos] sin conexion para producto {pid}: {exc}")
        OFFLINE_CACHE.mark_offline(str(exc))
        if request.method == "GET":
            fallback = OFFLINE_CACHE.get_products()
            for row in fallback:
                try:
                    row_id = int((row or {}).get("id") or 0)
                except Exception:
                    row_id = 0
                if row_id == int(pid):
                    return jsonify(enrich_product_with_alert(row))
            return jsonify({"error": "Producto no disponible sin conexión."}), 503
        return jsonify({"error": "No hay conexión a base de datos."}), 503
    try:
        if request.method == "GET":
            prod = fetch_product(conn, pid)
            if not prod:
                return jsonify({"error": "Producto no encontrado"}), 404
            return jsonify(enrich_product_with_alert(prod))
        if request.method == "DELETE":
            cur = conn.cursor()
            cur.execute("UPDATE productos SET activo=0 WHERE id=%s", (pid,))
            record_audit_event(
                cur,
                event_type="producto_desactivado",
                entity_type="producto",
                entity_id=pid,
                description=f"Producto #{pid} desactivado",
                details={"activo": False},
                actor_user_id=session.get("user_id"),
                actor_username=session.get("username"),
            )
            conn.commit()
            return jsonify({"success": True})
        current = fetch_product(conn, pid)
        if not current:
            return jsonify({"error": "Producto no encontrado"}), 404
        data = request.get_json(force=True) or {}
        try:
            product = validate_product_payload(data)
        except ValueError as exc:
            return jsonify({"success": False, "error": str(exc)}), 400
        try:
            image_blob, image_mime, image_changed = parse_product_image_data_url(
                data.get("imagen_data_url")
            )
        except ValueError as exc:
            return jsonify({"success": False, "error": str(exc)}), 400
        force = data.get("force", False)
        reason = (data.get("force_reason") or "").strip()
        old_price = float(current.get("precio") or 0.0)
        ratio = calculate_price_change_ratio(old_price, product["precio"])
        if ratio > PRICE_CHANGE_MAX_RATIO and not force:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "El cambio de precio excede el umbral permitido.",
                        "ratio": ratio,
                        "max_ratio": PRICE_CHANGE_MAX_RATIO,
                    }
                ),
                409,
            )
        if (
            ratio > PRICE_CHANGE_MAX_RATIO
            and force
            and len(reason) < PRICE_FORCE_REASON_MIN_LENGTH
        ):
            return (
                jsonify(
                    {
                        "success": False,
                        "error": f"Describe el motivo con al menos {PRICE_FORCE_REASON_MIN_LENGTH} caracteres.",
                    }
                ),
                400,
            )
        cur = conn.cursor()
        if image_changed:
            cur.execute(
                """
                UPDATE productos
                SET nombre=%s, categoria=%s, precio=%s, iva_percent=%s, stock=%s, min_stock=%s, imagen_blob=%s, imagen_mime=%s
                WHERE id=%s
                """,
                (
                    product["nombre"],
                    product["categoria"],
                    product["precio"],
                    product["iva_percent"],
                    product["stock"],
                    product["min_stock"],
                    image_blob,
                    image_mime,
                    pid,
                ),
            )
        else:
            cur.execute(
                """
                UPDATE productos
                SET nombre=%s, categoria=%s, precio=%s, iva_percent=%s, stock=%s, min_stock=%s
                WHERE id=%s
                """,
                (
                    product["nombre"],
                    product["categoria"],
                    product["precio"],
                    product["iva_percent"],
                    product["stock"],
                    product["min_stock"],
                    pid,
                ),
            )
        details = {
            "nombre": {"before": current.get("nombre"), "after": product["nombre"]},
            "categoria": {
                "before": current.get("categoria"),
                "after": product["categoria"],
            },
            "precio": {"before": old_price, "after": product["precio"]},
            "iva_percent": {
                "before": float(current.get("iva_percent") or DEFAULT_IVA_PERCENT),
                "after": float(product["iva_percent"]),
            },
            "stock": {"before": int(current.get("stock") or 0), "after": product["stock"]},
            "min_stock": {
                "before": int(current.get("min_stock") or 0),
                "after": product["min_stock"],
            },
        }
        if image_changed:
            image_before_state = "cargada" if current.get("imagen_url") else "sin_imagen"
            image_after_state = "cargada" if image_blob else "sin_imagen"
            details["imagen"] = {
                "before": image_before_state,
                "after": image_after_state,
                "action": (
                    "eliminada"
                    if image_before_state == "cargada" and image_after_state == "sin_imagen"
                    else "cargada"
                    if image_before_state == "sin_imagen" and image_after_state == "cargada"
                    else "reemplazada"
                ),
                "before_mime": current.get("imagen_mime"),
                "after_mime": image_mime,
            }
        description = build_product_update_audit_description(
            product.get("nombre"),
            details,
        )
        record_audit_event(
            cur,
            event_type="producto_actualizado",
            entity_type="producto",
            entity_id=pid,
            description=description,
            details=details,
            actor_user_id=session.get("user_id"),
            actor_username=session.get("username"),
        )
        conn.commit()
        if ratio > PRICE_CHANGE_MAX_RATIO and force:
            record_price_change(
                conn, pid, session.get("user_id"), old_price, product["precio"], reason
            )
        return jsonify({"success": True})
    finally:
        conn.close()


@app.route("/api/productos/<int:pid>/minimo", methods=["PUT"])
def api_producto_minimo(pid: int):
    """
    Actualizar stock minimo
    ---
    tags: [Productos]
    consumes:
      - application/json
    parameters:
      - in: path
        name: pid
        required: true
        type: integer
      - in: body
        name: body
        schema:
          type: object
          required:
            - min_stock
          properties:
            min_stock:
              type: integer
    responses:
      200:
        description: Minimo actualizado
      400:
        description: Datos invalidos
      403:
        description: Requiere rol administrador
    """
    permission_check = require_permission("products_manage")
    if permission_check:
        return permission_check
    data = request.get_json(force=True) or {}
    try:
        min_stock = coerce_int(data.get("min_stock"), "min_stock")
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    conn = get_db_conn()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT precio, stock, min_stock FROM productos WHERE id=%s", (pid,))
        prod = cur.fetchone()
        if not prod:
            return jsonify({"success": False, "error": "Producto no encontrado"}), 404
        cur.execute("UPDATE productos SET min_stock=%s WHERE id=%s", (min_stock, pid))
        record_audit_event(
            cur,
            event_type="producto_minimo_actualizado",
            entity_type="producto",
            entity_id=pid,
            description=f"Stock minimo actualizado para producto #{pid}",
            details={
                "min_stock": {
                    "before": int(prod.get("min_stock") or 0),
                    "after": int(min_stock),
                }
            },
            actor_user_id=session.get("user_id"),
            actor_username=session.get("username"),
        )
        conn.commit()
        prod.update({"id": pid, "min_stock": min_stock})
        return jsonify(
            {
                "success": True,
                "min_stock": min_stock,
                "alert": enrich_product_with_alert(prod),
            }
        )
    finally:
        conn.close()


@app.route("/api/verificar-stock", methods=["POST"])
def api_verificar_stock():
    """
    Verificar disponibilidad de stock
    ---
    tags:
      - Ventas
    consumes:
      - application/json
    parameters:
      - in: body
        name: body
        schema:
          type: object
          required:
            - items
          properties:
            items:
              type: array
              items:
                type: object
                properties:
                  id: {type: integer}
                  quantity: {type: integer}
    responses:
      200:
        description: Resultado de verificacion
    """
    permission_check = require_permission("sales_create")
    if permission_check:
        return permission_check
    payload = request.get_json(force=True) or {}
    items = payload.get("items") or []
    if not isinstance(items, list) or not items:
        return jsonify({"success": False, "stock_suficiente": False, "stock_actual": 0})
    conn = get_db_conn()
    try:
        cur = conn.cursor(dictionary=True)
        for item in items:
            try:
                product_id = int(item.get("id"))
                quantity = int(item.get("quantity"))
            except (TypeError, ValueError):
                return jsonify(
                    {"success": False, "stock_suficiente": False, "stock_actual": 0}
                )
            cur.execute(
                "SELECT nombre, stock FROM productos WHERE id=%s", (product_id,)
            )
            prod = cur.fetchone()
            if not prod or int(prod.get("stock") or 0) < quantity:
                return jsonify(
                    {
                        "success": True,
                        "stock_suficiente": False,
                        "stock_actual": int(prod.get("stock") or 0) if prod else 0,
                        "producto_id": product_id,
                        "producto_nombre": prod.get("nombre") if prod else "",
                    }
                )
        return jsonify({"success": True, "stock_suficiente": True})
    finally:
        conn.close()


@app.route("/api/inventario/movimientos", methods=["GET", "POST"])
def api_inventory_movements():
    permission_check = require_permission("products_manage")
    if permission_check:
        return permission_check
    conn = get_db_conn()
    try:
        cur = conn.cursor(dictionary=True)
        if request.method == "POST":
            payload = request.get_json(force=True) or {}
            try:
                product_id = int(payload.get("product_id"))
            except (TypeError, ValueError):
                return (
                    jsonify({"success": False, "error": "product_id invalido."}),
                    400,
                )
            movement_type = str(payload.get("tipo") or "ajuste").strip().lower()
            if movement_type not in {"entrada", "salida", "ajuste"}:
                return (
                    jsonify(
                        {
                            "success": False,
                            "error": "tipo invalido. Usa entrada, salida o ajuste.",
                        }
                    ),
                    400,
                )
            try:
                raw_qty = int(payload.get("cantidad"))
            except (TypeError, ValueError):
                return (
                    jsonify({"success": False, "error": "cantidad invalida."}),
                    400,
                )
            if raw_qty == 0:
                return (
                    jsonify(
                        {
                            "success": False,
                            "error": "cantidad debe ser diferente de cero.",
                        }
                    ),
                    400,
                )
            delta = raw_qty
            if movement_type == "entrada":
                delta = abs(raw_qty)
            elif movement_type == "salida":
                delta = -abs(raw_qty)
            reason = (payload.get("motivo") or "").strip()[:255]
            if not reason:
                reason = "Ajuste manual de inventario"
            conn.start_transaction()
            cur.execute(
                "SELECT id, nombre, stock FROM productos WHERE id=%s FOR UPDATE",
                (product_id,),
            )
            product = cur.fetchone()
            if not product:
                conn.rollback()
                return (
                    jsonify({"success": False, "error": "Producto no encontrado."}),
                    404,
                )
            stock_before = int(product.get("stock") or 0)
            stock_after = stock_before + delta
            if stock_after < 0:
                conn.rollback()
                return (
                    jsonify(
                        {
                            "success": False,
                            "error": "El movimiento genera stock negativo.",
                        }
                    ),
                    409,
                )
            cur.execute(
                "UPDATE productos SET stock=%s WHERE id=%s", (stock_after, product_id)
            )
            movement_id = record_inventory_movement(
                cur,
                producto_id=product_id,
                tipo=movement_type,
                cantidad=delta,
                stock_anterior=stock_before,
                stock_nuevo=stock_after,
                motivo=reason,
                usuario_id=session.get("user_id"),
            )
            record_audit_event(
                cur,
                event_type="inventario_movimiento",
                entity_type="producto",
                entity_id=product_id,
                description=(
                    f'Inventario {movement_type} en "{product.get("nombre")}" '
                    f"({stock_before} -> {stock_after})"
                ),
                details={
                    "tipo": movement_type,
                    "cantidad": delta,
                    "stock_anterior": stock_before,
                    "stock_nuevo": stock_after,
                    "motivo": reason,
                },
                actor_user_id=session.get("user_id"),
                actor_username=session.get("username"),
            )
            conn.commit()
            return jsonify(
                {
                    "success": True,
                    "id": movement_id,
                    "product_id": product_id,
                    "stock_before": stock_before,
                    "stock_after": stock_after,
                }
            )

        date_from = (request.args.get("from") or "").strip()
        date_to = (request.args.get("to") or "").strip()
        if bool(date_from) ^ bool(date_to):
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Para filtrar por fechas debes enviar from y to.",
                    }
                ),
                400,
            )
        if date_from:
            try:
                datetime.strptime(date_from, "%Y-%m-%d")
                datetime.strptime(date_to, "%Y-%m-%d")
            except ValueError:
                return (
                    jsonify(
                        {
                            "success": False,
                            "error": "Formato de fecha invalido. Usa YYYY-MM-DD.",
                        }
                    ),
                    400,
                )
        try:
            limit = int(request.args.get("limit", "100"))
        except (TypeError, ValueError):
            limit = 100
        limit = max(1, min(limit, 500))
        filters: List[str] = []
        params: List[Any] = []
        if date_from and date_to:
            filters.append("DATE(m.creado_en) BETWEEN %s AND %s")
            params.extend([date_from, date_to])
        where_sql = f"WHERE {' AND '.join(filters)}" if filters else ""
        query = f"""
            SELECT
                m.id,
                m.producto_id,
                p.nombre AS producto_nombre,
                m.tipo,
                m.cantidad,
                m.stock_anterior,
                m.stock_nuevo,
                m.motivo,
                m.usuario_id,
                u.username AS usuario,
                m.creado_en
            FROM inventario_movimientos m
            LEFT JOIN productos p ON p.id = m.producto_id
            LEFT JOIN usuarios u ON u.id = m.usuario_id
            {where_sql}
            ORDER BY m.id DESC
            LIMIT %s
        """
        params.append(limit)
        cur.execute(query, tuple(params))
        rows = cur.fetchall() or []
        summary = {
            "total": len(rows),
            "entrada": 0,
            "salida": 0,
            "ajuste": 0,
        }
        for row in rows:
            movement_type = str((row or {}).get("tipo") or "").lower().strip()
            if movement_type in summary:
                summary[movement_type] += 1
        return jsonify({"success": True, "movimientos": rows, "summary": summary})
    finally:
        conn.close()


@app.route("/api/ventas", methods=["POST"])
def api_ventas():
    """
    Registrar una venta
    ---
    tags:
      - Ventas
    consumes:
      - application/json
    parameters:
      - in: body
        name: body
        schema:
          type: object
          required:
            - items
            - payment_method
          properties:
            items:
              type: array
              items:
                type: object
                properties:
                  id: {type: integer}
                  quantity: {type: integer}
                  price: {type: number}
            payment_method:
              type: string
            force_price:
              type: boolean
            force_reason:
              type: string
    responses:
      200:
        description: Venta registrada
      400:
        description: Datos incompletos o invalidos
      401:
        description: No autenticado
    """
    permission_check = require_permission("sales_create")
    if permission_check:
        return permission_check
    payload = request.get_json(force=True) or {}
    items = payload.get("items") or []
    metodo_pago = payload.get("payment_method")
    force_price = payload.get("force_price", False)
    force_reason = (payload.get("force_reason") or "").strip()
    if not items or not metodo_pago:
        return jsonify({"success": False, "message": "Datos incompletos"}), 400
    conn = get_db_conn()
    transaction_started = False
    cur = None

    def abort_sale(message: str, status: int = 400, **extra):
        response_payload = {"success": False, "message": message}
        response_payload.update(extra)
        if transaction_started:
            try:
                conn.rollback()
            except Exception:
                pass
        return jsonify(response_payload), status

    try:
        cur = conn.cursor(dictionary=True)
        try:
            conn.start_transaction()
            transaction_started = True
        except Exception:
            transaction_started = False
        cur.execute(
            """
            INSERT INTO ventas (fecha, usuario_id, metodo_pago, total)
            VALUES (NOW(), %s, %s, 0)
            """,
            (session["user_id"], metodo_pago),
        )
        venta_id = cur.lastrowid
        configured_iva_percent = get_configured_iva_percent(cur)
        subtotal_total = Decimal("0.00")
        iva_total = Decimal("0.00")
        item_iva_rates: set[Decimal] = set()
        seen_ids = set()
        audit_trail: List[Tuple[int, float, float]] = []
        for item in items:
            try:
                product_id = int(item.get("id"))
                quantity = int(item.get("quantity"))
            except (TypeError, ValueError):
                return abort_sale("Datos de productos invalidos")
            if quantity <= 0:
                return abort_sale(f"Cantidad invalida para producto ID {product_id}")
            if product_id in seen_ids:
                return abort_sale(
                    "No se permiten productos duplicados en la misma venta"
                )
            seen_ids.add(product_id)
            cur.execute(
                "SELECT nombre, precio, stock, iva_percent FROM productos WHERE id=%s FOR UPDATE",
                (product_id,),
            )
            prod = cur.fetchone()
            if not prod:
                return abort_sale(f"Producto {product_id} no encontrado", status=404)
            precio_base = normalize_price(coerce_decimal(prod["precio"], "precio"))
            stock_disponible = coerce_int(prod["stock"], "stock")
            try:
                line_iva_percent = normalize_iva(
                    Decimal(str(prod.get("iva_percent")))
                )
            except Exception:
                line_iva_percent = configured_iva_percent
            client_price_raw = item.get("price")
            if client_price_raw is not None:
                try:
                    client_price = normalize_price(
                        coerce_decimal(client_price_raw, "precio")
                    )
                except ValueError:
                    return abort_sale(
                        f"Precio enviado para producto ID {product_id} no es valido."
                    )
                ratio = calculate_price_change_ratio(
                    float(precio_base), float(client_price)
                )
                if ratio > PRICE_CHANGE_MAX_RATIO and not force_price:
                    return abort_sale(
                        f"Precio modificado para producto ID {product_id} supera el limite permitido.",
                        status=409,
                        ratio=ratio,
                        max_ratio=PRICE_CHANGE_MAX_RATIO,
                    )
                if (
                    ratio > PRICE_CHANGE_MAX_RATIO
                    and force_price
                    and len(force_reason) < PRICE_FORCE_REASON_MIN_LENGTH
                ):
                    return abort_sale(
                        f"Describe el motivo con al menos {PRICE_FORCE_REASON_MIN_LENGTH} caracteres."
                    )
                precio_unitario = client_price
                audit_trail.append(
                    (product_id, float(precio_base), float(precio_unitario))
                )
            else:
                precio_unitario = precio_base
            if stock_disponible < quantity:
                return abort_sale(f"Stock insuficiente para producto ID {product_id}")
            line_subtotal = normalize_price(precio_unitario * Decimal(quantity))
            unit_iva = normalize_price(
                (precio_unitario * line_iva_percent) / Decimal("100")
            )
            line_iva = normalize_price(unit_iva * Decimal(quantity))
            subtotal_total += line_subtotal
            iva_total += line_iva
            item_iva_rates.add(line_iva_percent)
            cur.execute(
                """
                INSERT INTO venta_detalle (venta_id, producto_id, cantidad, precio, iva_percent)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    venta_id,
                    product_id,
                    quantity,
                    float(precio_unitario),
                    float(line_iva_percent),
                ),
            )
            cur.execute(
                "UPDATE productos SET stock = stock - %s WHERE id=%s",
                (quantity, product_id),
            )
            stock_nuevo = stock_disponible - quantity
            record_inventory_movement(
                cur,
                producto_id=product_id,
                tipo="salida",
                cantidad=-quantity,
                stock_anterior=stock_disponible,
                stock_nuevo=stock_nuevo,
                motivo=f"Venta #{venta_id}",
                usuario_id=session.get("user_id"),
            )
        subtotal_total = normalize_price(subtotal_total)
        iva_total = normalize_price(iva_total)
        total = normalize_price(subtotal_total + iva_total)
        sale_iva_percent = next(iter(item_iva_rates)) if len(item_iva_rates) == 1 else Decimal("0.00")
        cur.execute(
            "UPDATE ventas SET total=%s, iva_percent=%s WHERE id=%s",
            (float(total), float(sale_iva_percent), venta_id),
        )
        response_iva_percent = (
            float(sale_iva_percent) if len(item_iva_rates) == 1 else None
        )
        iva_mode = "por_producto" if len(item_iva_rates) > 1 else "global"
        record_audit_event(
            cur,
            event_type="venta_registrada",
            entity_type="venta",
            entity_id=venta_id,
            description=f"Venta #{venta_id} registrada por {format_export_currency(total)}",
            details={
                "metodo_pago": metodo_pago,
                "subtotal": float(subtotal_total),
                "iva_total": float(iva_total),
                "total": float(total),
                "iva_percent": response_iva_percent,
                "iva_mode": iva_mode,
                "items": len(items),
            },
            actor_user_id=session.get("user_id"),
            actor_username=session.get("username"),
        )
        if audit_trail:
            for product_id, old_price, new_price in audit_trail:
                record_price_change(
                    conn,
                    product_id,
                    session.get("user_id"),
                    old_price,
                    new_price,
                    force_reason if force_price else "Ajuste de precio en venta",
                )
        recommendations_payload: Dict[str, Any] = {}
        try:
            sales_snapshot = load_sales_from_db(DB_CONFIG)
            if sales_snapshot is not None and not sales_snapshot.empty:
                analysis = Recommender(sales_snapshot)
                rec_data = analysis.analyze_sales() or {}
                combos = rec_data.get("combo_suggestions") or []
                restock = rec_data.get("restock_alerts") or []
                recommendations_payload = {
                    "combo_suggestions": combos[:3],
                    "restock_alerts": restock[:3],
                }
                notifier = Notifier()
                if combos:
                    try:
                        notifier.send_combo_suggestions(combos[:3])
                    except Exception as combo_exc:
                        print(f"[ventas] no se pudo notificar combos: {combo_exc}")
                if restock:
                    try:
                        notifier.send_restock_alerts(restock[:3])
                    except Exception as restock_exc:
                        print(
                            f"[ventas] no se pudo notificar reposicion: {restock_exc}"
                        )
                store_sale_recommendations(cur, venta_id, combos[:3], restock[:3])
        except Exception as rec_exc:
            print(f"[ventas] recomendaciones IA no disponibles: {rec_exc}")
            recommendations_payload = {}
        if transaction_started:
            conn.commit()
        response = {
            "success": True,
            "total": round(float(total), 2),
            "venta_id": venta_id,
            "totals": {
                "subtotal": round(float(subtotal_total), 2),
                "iva": round(float(iva_total), 2),
                "total": round(float(total), 2),
                "iva_percent": response_iva_percent,
                "iva_mode": iva_mode,
            },
        }
        if recommendations_payload:
            response["recommendations"] = recommendations_payload
        return jsonify(response)
    except Exception as exc:
        print(f"[ventas] error registrando venta: {exc}")
        return abort_sale("No se pudo registrar la venta", status=500)
    finally:
        if cur is not None:
            try:
                cur.close()
            except Exception:
                pass
        conn.close()


def load_sales_report_payload(date_from_raw: str, date_to_raw: str) -> Dict[str, Any]:
    viewer_role = None
    viewer_user_id = None
    viewer_username = None
    if has_request_context():
        viewer_role = str(session.get("role") or "").strip().lower() or None
        viewer_user_id = session.get("user_id")
        viewer_username = session.get("username")
    return reporting_utils.load_sales_report_payload(
        date_from_raw,
        date_to_raw,
        get_db_conn=get_db_conn,
        offline_cache=OFFLINE_CACHE,
        build_ai_report_payload=build_ai_report_payload,
        viewer_role=viewer_role,
        viewer_user_id=viewer_user_id,
        viewer_username=viewer_username,
    )


def load_product_stats_payload(
    *,
    date_from_raw: Optional[str] = None,
    date_to_raw: Optional[str] = None,
    periodo: str = "mes",
) -> Dict[str, Any]:
    return reporting_utils.load_product_stats_payload(
        date_from_raw=date_from_raw,
        date_to_raw=date_to_raw,
        periodo=periodo,
        get_db_conn=get_db_conn,
        offline_cache=OFFLINE_CACHE,
    )

def serialize_audit_entry(row: Dict[str, Any]) -> Dict[str, Any]:
    return audit_trail_utils.serialize_audit_entry(
        row,
        normalize_event_type=normalize_audit_event_type,
        parse_json_object_fn=parse_json_object,
        bogota_isoformat=bogota_isoformat,
    )


def fetch_audit_event_rows(conn, *, limit: int) -> List[Dict[str, Any]]:
    return audit_trail_utils.fetch_audit_event_rows(
        conn,
        limit=limit,
        ensure_audit_events_table=ensure_audit_events_table,
        ensure_users_table=ensure_users_table,
        serialize_entry=serialize_audit_entry,
    )


def fetch_legacy_price_audit_rows(conn, *, limit: int) -> List[Dict[str, Any]]:
    return audit_trail_utils.fetch_legacy_price_audit_rows(
        conn,
        limit=limit,
        ensure_price_audit_table=ensure_price_audit_table,
        ensure_users_table=ensure_users_table,
        serialize_entry=serialize_audit_entry,
    )


def fetch_legacy_inventory_audit_rows(conn, *, limit: int) -> List[Dict[str, Any]]:
    return audit_trail_utils.fetch_legacy_inventory_audit_rows(
        conn,
        limit=limit,
        ensure_inventory_movements_table=ensure_inventory_movements_table,
        ensure_users_table=ensure_users_table,
        serialize_entry=serialize_audit_entry,
    )


def audit_entry_matches_filters(
    entry: Dict[str, Any],
    *,
    action_filter: Optional[set[str]],
    user_filter: str,
    start_date: Optional[datetime],
    end_date: Optional[datetime],
    include_system: bool,
) -> bool:
    return audit_trail_utils.audit_entry_matches_filters(
        entry,
        action_filter=action_filter,
        user_filter=user_filter,
        start_date=start_date,
        end_date=end_date,
        include_system=include_system,
        normalize_event_type=normalize_audit_event_type,
        to_bogota_datetime=to_bogota_datetime,
    )


def audit_entry_sort_key(entry: Dict[str, Any]) -> Tuple[datetime, int]:
    return audit_trail_utils.audit_entry_sort_key(
        entry,
        to_bogota_datetime=to_bogota_datetime,
        min_datetime=datetime.min.replace(tzinfo=BOGOTA_TZ),
    )


def load_audit_trail_payload(
    *,
    date_from_raw: Optional[str] = None,
    date_to_raw: Optional[str] = None,
    action_raw: Optional[str] = None,
    user_raw: Optional[str] = None,
    limit_raw: Optional[str] = None,
    include_system_raw: Optional[str] = None,
) -> Dict[str, Any]:
    return audit_trail_utils.load_audit_trail_payload(
        date_from_raw=date_from_raw,
        date_to_raw=date_to_raw,
        action_raw=action_raw,
        user_raw=user_raw,
        limit_raw=limit_raw,
        include_system_raw=include_system_raw,
        parse_requested_date_range=parse_requested_date_range,
        parse_limit=parse_int_limit,
        resolve_action_filter=resolve_audit_action_filter,
        get_db_conn=get_db_conn,
        fetch_audit_events=fetch_audit_event_rows,
        fetch_legacy_price=fetch_legacy_price_audit_rows,
        fetch_legacy_inventory=fetch_legacy_inventory_audit_rows,
        matches_filters=audit_entry_matches_filters,
        sort_key=audit_entry_sort_key,
        normalize_event_type=normalize_audit_event_type,
    )


def format_export_currency(value: Any) -> str:
    try:
        amount = float(value or 0.0)
    except (TypeError, ValueError):
        amount = 0.0
    return "${:,.2f}".format(amount)


def pdf_safe_text(value: Any) -> str:
    return str(value or "").encode("latin-1", "replace").decode("latin-1")


def build_sales_report_export_file(
    payload: Dict[str, Any], export_format: str
) -> Tuple[io.BytesIO, str, str]:
    return report_export_utils.build_sales_report_export_file(
        payload,
        export_format,
        pdf_safe_text=pdf_safe_text,
        format_currency=format_export_currency,
    )


def build_product_stats_export_file(
    payload: Dict[str, Any], export_format: str
) -> Tuple[io.BytesIO, str, str]:
    return report_export_utils.build_product_stats_export_file(
        payload,
        export_format,
        pdf_safe_text=pdf_safe_text,
        format_currency=format_export_currency,
    )


def build_audit_export_file(
    payload: Dict[str, Any], export_format: str
) -> Tuple[io.BytesIO, str, str]:
    return report_export_utils.build_audit_export_file(
        payload,
        export_format,
        pdf_safe_text=pdf_safe_text,
        build_entity_label=build_audit_entity_label,
        build_actor_label=build_audit_actor_label,
    )
def build_dashboard_snapshot_payload(
    snapshot: Dict[str, Any],
    *,
    payment_start: Any,
    payment_end: Any,
    payment_period: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    return dashboard_data_utils.build_dashboard_snapshot_payload(
        snapshot,
        payment_start=payment_start,
        payment_end=payment_end,
        payment_period=payment_period,
        get_sales_report=OFFLINE_CACHE.get_sales_report,
        build_payment_breakdown_from_sales=build_payment_breakdown_from_sales,
        product_needs_stock_alert=product_needs_stock_alert,
        enrich_product_with_alert=enrich_product_with_alert,
        build_purchase_recommendations=build_purchase_recommendations,
        enrich_dashboard_payload=enrich_dashboard_payload,
    )


def load_dashboard_payload(
    conn,
    *,
    payment_period: Optional[Dict[str, Any]],
    payment_from: Optional[str],
    payment_to: Optional[str],
) -> Dict[str, Any]:
    return dashboard_data_utils.load_dashboard_payload(
        conn,
        payment_period=payment_period,
        payment_from=payment_from,
        payment_to=payment_to,
        enrich_product_with_alert=enrich_product_with_alert,
        build_purchase_recommendations=build_purchase_recommendations,
        enrich_dashboard_payload=enrich_dashboard_payload,
        mark_online=OFFLINE_CACHE.mark_online,
    )


@app.route("/api/dashboard", methods=["GET"])
def api_dashboard():
    """
    Resumen del dashboard
    ---
    tags:
      - Reportes
    responses:
      200:
        description: Datos consolidados
      401:
        description: No autenticado
    """
    permission_check = require_permission("dashboard_view")
    if permission_check:
        return permission_check
    try:
        payment_from, payment_to, payment_start, payment_end = parse_requested_date_range(
            request.args.get("from"),
            request.args.get("to"),
            required=False,
        )
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    payment_period = (
        {"desde": payment_from, "hasta": payment_to}
        if payment_from and payment_to
        else None
    )

    try:
        conn = get_db_conn()
    except Exception as exc:
        print(f"[dashboard] no se pudo abrir conexion: {exc}")
        OFFLINE_CACHE.mark_offline(str(exc))
        snapshot = OFFLINE_CACHE.get_dashboard_snapshot()
        if snapshot:
            response = jsonify(
                build_dashboard_snapshot_payload(
                    snapshot,
                    payment_start=payment_start,
                    payment_end=payment_end,
                    payment_period=payment_period,
                )
            )
            response.headers["X-Data-Source"] = "offline-cache"
            return response
        return jsonify({"error": "Dashboard no disponible sin conexión."}), 503
    try:
        return jsonify(
            load_dashboard_payload(
                conn,
                payment_period=payment_period,
                payment_from=payment_from,
                payment_to=payment_to,
            )
        )
    except Exception as exc:
        print(f"[dashboard] error consultando datos: {exc}")
        OFFLINE_CACHE.mark_offline(str(exc))
        snapshot = OFFLINE_CACHE.get_dashboard_snapshot()
        if snapshot:
            response = jsonify(
                build_dashboard_snapshot_payload(
                    snapshot,
                    payment_start=payment_start,
                    payment_end=payment_end,
                    payment_period=payment_period,
                )
            )
            response.headers["X-Data-Source"] = "offline-cache"
            return response
        return jsonify({"error": "Dashboard no disponible sin conexión."}), 503
    finally:
        conn.close()


@app.route("/api/reportes/ventas", methods=["GET"])
def api_reportes_ventas():
    """
    Generar reporte de ventas por periodo
    ---
    tags:
      - Reportes
    parameters:
      - in: query
        name: from
        required: true
        type: string
        description: Fecha inicial (YYYY-MM-DD)
      - in: query
        name: to
        required: true
        type: string
        description: Fecha final (YYYY-MM-DD)
    responses:
      200:
        description: Reporte generado
      400:
        description: Parametros invalidos
      401:
        description: No autenticado
    """
    permission_check = require_permission("reports_view")
    if permission_check:
        return permission_check
    try:
        payload = load_sales_report_payload(
            request.args.get("from"),
            request.args.get("to"),
        )
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except RuntimeError as exc:
        return jsonify({"success": False, "error": str(exc)}), 503
    response = jsonify(payload)
    if payload.get("offline"):
        response.headers["X-Data-Source"] = "offline-cache"
    return response


@app.route("/api/reportes/ventas/export", methods=["GET"])
def api_reportes_ventas_export():
    permission_check = require_permission("reports_view")
    if permission_check:
        return permission_check
    try:
        payload = load_sales_report_payload(
            request.args.get("from"),
            request.args.get("to"),
        )
        export_format = normalize_export_format(request.args.get("format"))
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except RuntimeError as exc:
        return jsonify({"success": False, "error": str(exc)}), 503
    output, mimetype, extension = build_sales_report_export_file(
        payload,
        export_format,
    )
    period = payload.get("periodo") or {}
    filename = (
        f"reporte-ventas-{period.get('desde') or 'sin-fecha'}-a-"
        f"{period.get('hasta') or 'sin-fecha'}.{extension}"
    )
    try:
        conn = get_db_conn()
    except Exception:
        conn = None
    try:
        try_record_audit_event(
            conn,
            event_type="reporte_exportado",
            entity_type="reporte",
            entity_id=None,
            description="Exportación de reporte de ventas",
            details={
                "format": export_format,
                "from": period.get("desde"),
                "to": period.get("hasta"),
            },
            actor_user_id=session.get("user_id"),
            actor_username=session.get("username"),
        )
    finally:
        if conn:
            conn.close()
    return send_file(
        output,
        mimetype=mimetype,
        as_attachment=True,
        download_name=filename,
    )


@app.route("/api/estadisticas/productos-mas-vendidos", methods=["GET"])
def api_estadisticas_productos():
    """
    Estadisticas de productos mas vendidos
    ---
    tags:
      - Reportes
    parameters:
      - in: query
        name: periodo
        required: false
        type: string
        description: Valores admitidos semana o mes
    responses:
      200:
        description: Estadisticas generadas
      401:
        description: No autenticado
    """
    permission_check = require_permission("statistics_view")
    if permission_check:
        return permission_check
    try:
        payload = load_product_stats_payload(
            date_from_raw=request.args.get("from"),
            date_to_raw=request.args.get("to"),
            periodo=request.args.get("periodo", "mes"),
        )
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except RuntimeError as exc:
        return jsonify({"success": False, "error": str(exc)}), 503
    response = jsonify(payload)
    if payload.get("offline"):
        response.headers["X-Data-Source"] = "offline-cache"
    return response


@app.route("/api/estadisticas/productos-mas-vendidos/export", methods=["GET"])
def api_estadisticas_productos_export():
    permission_check = require_permission("statistics_view")
    if permission_check:
        return permission_check
    try:
        payload = load_product_stats_payload(
            date_from_raw=request.args.get("from"),
            date_to_raw=request.args.get("to"),
            periodo=request.args.get("periodo", "mes"),
        )
        export_format = normalize_export_format(request.args.get("format"))
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except RuntimeError as exc:
        return jsonify({"success": False, "error": str(exc)}), 503
    output, mimetype, extension = build_product_stats_export_file(
        payload,
        export_format,
    )
    period = payload.get("period") or {}
    if period:
        filename = (
            f"reporte-estadisticas-{period.get('desde') or 'sin-fecha'}-a-"
            f"{period.get('hasta') or 'sin-fecha'}.{extension}"
        )
    else:
        filename = f"reporte-estadisticas-{payload.get('periodo') or 'general'}.{extension}"
    try:
        conn = get_db_conn()
    except Exception:
        conn = None
    try:
        try_record_audit_event(
            conn,
            event_type="estadisticas_exportadas",
            entity_type="reporte",
            entity_id=None,
            description="Exportación de estadísticas de productos",
            details={
                "format": export_format,
                "periodo": payload.get("periodo"),
                "period": period,
            },
            actor_user_id=session.get("user_id"),
            actor_username=session.get("username"),
        )
    finally:
        if conn:
            conn.close()
    return send_file(
        output,
        mimetype=mimetype,
        as_attachment=True,
        download_name=filename,
    )


@app.route("/api/auditoria", methods=["GET"])
def api_auditoria():
    permission_check = require_permission("audit_view")
    if permission_check:
        return permission_check
    try:
        payload = load_audit_trail_payload(
            date_from_raw=request.args.get("from"),
            date_to_raw=request.args.get("to"),
            action_raw=request.args.get("action"),
            user_raw=request.args.get("user"),
            limit_raw=request.args.get("limit"),
            include_system_raw=request.args.get("include_system"),
        )
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    return jsonify(payload)


@app.route("/api/auditoria/export", methods=["GET"])
def api_auditoria_export():
    permission_check = require_permission("audit_view")
    if permission_check:
        return permission_check
    try:
        payload = load_audit_trail_payload(
            date_from_raw=request.args.get("from"),
            date_to_raw=request.args.get("to"),
            action_raw=request.args.get("action"),
            user_raw=request.args.get("user"),
            limit_raw=request.args.get("limit") or "2000",
            include_system_raw=request.args.get("include_system"),
        )
        export_format = normalize_export_format(request.args.get("format"))
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    output, mimetype, extension = build_audit_export_file(payload, export_format)
    summary = payload.get("summary") or {}
    period = summary.get("periodo") or {}
    if period:
        filename = (
            f"reporte-auditoria-{period.get('desde') or 'sin-fecha'}-a-"
            f"{period.get('hasta') or 'sin-fecha'}.{extension}"
        )
    else:
        filename = f"reporte-auditoria-general.{extension}"
    try:
        conn = get_db_conn()
    except Exception:
        conn = None
    try:
        try_record_audit_event(
            conn,
            event_type="auditoria_exportada",
            entity_type="reporte",
            entity_id=None,
            description="Exportación de auditoría",
            details={
                "format": export_format,
                "period": period,
                "action": summary.get("action"),
                "user": summary.get("user"),
            },
            actor_user_id=session.get("user_id"),
            actor_username=session.get("username"),
        )
    finally:
        if conn:
            conn.close()
    return send_file(
        output,
        mimetype=mimetype,
        as_attachment=True,
        download_name=filename,
    )

def build_offline_sale_detail_payload(offline: Dict[str, Any]) -> Dict[str, Any]:
    return sale_detail_utils.build_offline_sale_detail_payload(offline)


def build_sale_detail_payload(
    venta: Dict[str, Any],
    raw_items: List[Dict[str, Any]],
    rec_row: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    return sale_detail_utils.build_sale_detail_payload(
        venta,
        raw_items,
        rec_row,
        normalize_iva=normalize_iva,
        normalize_price=normalize_price,
        bogota_isoformat=bogota_isoformat,
        json_loads=json.loads,
    )


def load_sale_detail_payload(conn, venta_id: int) -> Optional[Dict[str, Any]]:
    return sale_detail_utils.load_sale_detail_payload(
        conn,
        venta_id,
        build_sale_detail_payload=build_sale_detail_payload,
        mark_online=OFFLINE_CACHE.mark_online,
    )


def fetch_recent_sales_rows(
    conn,
    *,
    limit: int = 20,
    viewer_role: Any,
    viewer_user_id: Any,
) -> List[Dict[str, Any]]:
    return sale_void_utils.fetch_recent_sales_rows(
        conn,
        limit=limit,
        viewer_role=viewer_role,
        viewer_user_id=viewer_user_id,
    )


def build_sale_capabilities(
    sale: Dict[str, Any],
    *,
    viewer_role: Any,
    viewer_user_id: Any,
) -> Dict[str, bool]:
    return sale_void_utils.build_sale_capabilities(
        sale,
        viewer_role=viewer_role,
        viewer_user_id=viewer_user_id,
    )


def load_sale_void_context(cur, sale_id: int) -> Optional[Dict[str, Any]]:
    return sale_void_utils.load_sale_void_context(cur, sale_id)


def authorize_sale_void(
    cur,
    *,
    sale_id: int,
    manager_key: str,
    actor_user_id: Optional[int],
    actor_username: Optional[str],
) -> Dict[str, Any]:
    return sale_void_utils.authorize_sale_void(
        cur,
        sale_id=sale_id,
        manager_key=manager_key,
        actor_user_id=actor_user_id,
        actor_username=actor_username,
        auth_key=sale_void_utils.SALE_VOID_AUTH_KEY,
        load_sale_context=load_sale_void_context,
        record_audit_event=record_audit_event,
    )


def disable_sale(
    cur,
    *,
    sale_id: int,
    actor_role: Any,
    actor_user_id: Optional[int],
    actor_username: Optional[str],
    reason: str,
) -> Dict[str, Any]:
    return sale_void_utils.void_sale(
        cur,
        sale_id=sale_id,
        actor_role=actor_role,
        actor_user_id=actor_user_id,
        actor_username=actor_username,
        reason=reason,
        load_sale_context=load_sale_void_context,
        record_inventory_movement=record_inventory_movement,
        record_audit_event=record_audit_event,
    )


@app.route("/api/ventas/recientes", methods=["GET"])
def api_recent_sales():
    permission_check = require_permission("sales_view")
    if permission_check:
        return permission_check
    try:
        limit = int(request.args.get("limit", "20"))
    except (TypeError, ValueError):
        limit = 20
    limit = max(1, min(limit, 100))
    try:
        conn = get_db_conn()
    except Exception as exc:
        print(f"[ventas] error abriendo ventas recientes: {exc}")
        OFFLINE_CACHE.mark_offline(str(exc))
        return jsonify({"success": False, "error": "No se pudieron cargar las ventas."}), 503
    try:
        ventas = fetch_recent_sales_rows(
            conn,
            limit=limit,
            viewer_role=session.get("role"),
            viewer_user_id=session.get("user_id"),
        )
        OFFLINE_CACHE.mark_online()
    except Exception as exc:
        print(f"[ventas] error consultando ventas recientes: {exc}")
        OFFLINE_CACHE.mark_offline(str(exc))
        return jsonify({"success": False, "error": "No se pudieron cargar las ventas."}), 500
    finally:
        conn.close()
    for venta in ventas:
        venta["anulada"] = bool(venta.get("anulada"))
        venta["anulacion_autorizada"] = bool(venta.get("anulacion_autorizada"))
    return jsonify({"success": True, "ventas": ventas})


@app.route("/api/ventas/<int:venta_id>", methods=["GET"])
def api_venta_detalle(venta_id: int):
    """
    Obtener detalle de una venta
    ---
    tags:
      - Ventas
    parameters:
      - in: path
        name: venta_id
        required: true
        type: integer
    responses:
      200:
        description: Venta encontrada
      401:
        description: No autenticado
      404:
        description: Venta no encontrada
    """
    permission_check = require_permission("sales_view")
    if permission_check:
        return permission_check
    try:
        conn = get_db_conn()
    except Exception as exc:
        print(f"[ventas] no se pudo abrir conexion: {exc}")
        offline = OFFLINE_CACHE.get_sale_detail(venta_id)
        if offline:
            payload = build_offline_sale_detail_payload(offline)
            payload["capabilities"] = build_sale_capabilities(
                payload.get("venta") or {},
                viewer_role=session.get("role"),
                viewer_user_id=session.get("user_id"),
            )
            return jsonify(payload)
        OFFLINE_CACHE.mark_offline(str(exc))
        return jsonify({"error": "No se pudo obtener el detalle."}), 503
    try:
        payload = load_sale_detail_payload(conn, venta_id)
        if not payload:
            return jsonify({"error": "Venta no encontrada"}), 404
        sale_data = payload.get("venta") or {}
        capabilities = build_sale_capabilities(
            sale_data,
            viewer_role=session.get("role"),
            viewer_user_id=session.get("user_id"),
        )
        payload["capabilities"] = capabilities
    finally:
        conn.close()
    return jsonify(payload)


@app.route("/api/ventas/<int:venta_id>/autorizar-deshabilitacion", methods=["POST"])
def api_sale_authorize_disable(venta_id: int):
    if not check_login():
        return jsonify({"success": False, "error": "No autenticado"}), 401
    role = str(session.get("role") or "").strip().lower()
    if role not in {"gerente", "admin"}:
        return (
            jsonify(
                {
                    "success": False,
                    "error": "Solo gerente o admin pueden autorizar esta accion.",
                }
            ),
            403,
        )
    payload = request.get_json(force=True) or {}
    manager_key = (payload.get("clave") or "").strip()
    if not manager_key:
        return jsonify({"success": False, "error": "La clave es obligatoria."}), 400
    try:
        conn = get_db_conn()
    except Exception as exc:
        print(f"[ventas] error abriendo autorizacion de venta: {exc}")
        return (
            jsonify(
                {
                    "success": False,
                    "error": "No se pudo autorizar la deshabilitacion de la venta.",
                }
            ),
            503,
        )
    try:
        cur = conn.cursor(dictionary=True)
        try:
            conn.start_transaction()
        except Exception:
            pass
        result = authorize_sale_void(
            cur,
            sale_id=venta_id,
            manager_key=manager_key,
            actor_user_id=session.get("user_id"),
            actor_username=session.get("username"),
        )
        conn.commit()
        return jsonify(
            {
                "success": True,
                "message": f"Venta #{venta_id} habilitada para deshabilitacion por el vendedor.",
                **result,
            }
        )
    except LookupError as exc:
        conn.rollback()
        return jsonify({"success": False, "error": str(exc)}), 404
    except PermissionError as exc:
        conn.rollback()
        return jsonify({"success": False, "error": str(exc)}), 403
    except ValueError as exc:
        conn.rollback()
        return jsonify({"success": False, "error": str(exc)}), 409
    except Exception as exc:
        conn.rollback()
        print(f"[ventas] error autorizando deshabilitacion: {exc}")
        return (
            jsonify(
                {
                    "success": False,
                    "error": "No se pudo autorizar la deshabilitacion de la venta.",
                }
            ),
            500,
        )
    finally:
        conn.close()


@app.route("/api/ventas/<int:venta_id>/deshabilitar", methods=["POST"])
def api_sale_disable(venta_id: int):
    if not check_login():
        return jsonify({"success": False, "error": "No autenticado"}), 401
    role = str(session.get("role") or "").strip().lower()
    if role not in {"vendedor", "admin"}:
        return (
            jsonify(
                {
                    "success": False,
                    "error": "Solo vendedor o admin pueden deshabilitar ventas.",
                }
            ),
            403,
        )
    payload = request.get_json(force=True) or {}
    reason = (payload.get("motivo") or "").strip()
    try:
        conn = get_db_conn()
    except Exception as exc:
        print(f"[ventas] error abriendo deshabilitacion de venta: {exc}")
        return (
            jsonify(
                {
                    "success": False,
                    "error": "No se pudo deshabilitar la venta.",
                }
            ),
            503,
        )
    try:
        cur = conn.cursor(dictionary=True)
        try:
            conn.start_transaction()
        except Exception:
            pass
        result = disable_sale(
            cur,
            sale_id=venta_id,
            actor_role=role,
            actor_user_id=session.get("user_id"),
            actor_username=session.get("username"),
            reason=reason,
        )
        conn.commit()
        OFFLINE_CACHE.mark_online()
        return jsonify(
            {
                "success": True,
                "message": f"Venta #{venta_id} deshabilitada correctamente.",
                **result,
            }
        )
    except LookupError as exc:
        conn.rollback()
        return jsonify({"success": False, "error": str(exc)}), 404
    except PermissionError as exc:
        conn.rollback()
        return jsonify({"success": False, "error": str(exc)}), 403
    except ValueError as exc:
        conn.rollback()
        return jsonify({"success": False, "error": str(exc)}), 409
    except Exception as exc:
        conn.rollback()
        print(f"[ventas] error deshabilitando venta: {exc}")
        return (
            jsonify(
                {
                    "success": False,
                    "error": "No se pudo deshabilitar la venta.",
                }
            ),
            500,
        )
    finally:
        conn.close()


def load_sales_dataframe_for_ai(
    date_from: Optional[str] = None, date_to: Optional[str] = None
) -> Optional[pd.DataFrame]:
    df = load_sales_from_db(DB_CONFIG, date_from=date_from, date_to=date_to)
    if df is None or df.empty:
        csv_path = find_existing_sales_csv("data/sales_data.csv")
        if csv_path:
            try:
                df = load_sales_data(csv_path)
            except Exception as exc:
                print(f"[ia] error cargando CSV: {exc}")
                df = None
        else:
            df = None
    if (df is None or df.empty) and OFFLINE_CACHE.has_snapshot():
        offline_df = OFFLINE_CACHE.get_sales_dataframe()
        if offline_df is not None and not offline_df.empty:
            print("[ia] usando respaldo offline para analítica.")
            return offline_df
    return df


def fetch_inventory_snapshot() -> List[Dict[str, Any]]:
    conn = None
    try:
        conn = get_db_conn()
        ensure_runtime_schema(conn)
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT
                id,
                nombre,
                categoria,
                precio,
                iva_percent,
                stock,
                min_stock,
                activo,
                imagen_mime,
                REPLACE(TO_BASE64(imagen_blob), '\n', '') AS imagen_b64
            FROM productos
            """
        )
        rows = cur.fetchall() or []
        OFFLINE_CACHE.mark_online()
        return rows
    except Exception as exc:
        print(f"[ia] error consultando inventario: {exc}")
        OFFLINE_CACHE.mark_offline(str(exc))
        fallback = OFFLINE_CACHE.get_products()
        if fallback:
            return fallback
        return []
    finally:
        if conn:
            conn.close()


def build_product_catalog_snapshot() -> List[Dict[str, Any]]:
    return chat_query_utils.build_product_catalog_snapshot(fetch_inventory_snapshot())


def handle_custom_chat_request(
    question: str, sales_df: Optional[pd.DataFrame]
) -> Optional[str]:
    return chat_query_utils.handle_custom_chat_request(
        question,
        sales_df,
        fetch_inventory_snapshot(),
    )


def store_ai_report_log(
    payload: Dict[str, Any], fuente: str = "manual", version: str = "analytics_v1"
) -> int:
    conn = get_db_conn()
    try:
        cur = conn.cursor()
        ensure_ai_logs_table(cur)
        fecha = payload.get("fecha_ejecucion")
        if not fecha:
            fecha = datetime.now(BOGOTA_TZ).date().isoformat()
        cur.execute(
            """
            INSERT INTO tabla_logs_ia (fecha_ejecucion, payload_json, fuente, version)
            VALUES (%s, %s, %s, %s)
            """,
            (fecha, json.dumps(payload, ensure_ascii=False), fuente, version),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


@app.route("/api/ia/reportes", methods=["POST"])
def api_ia_generate_report():
    admin_check = require_admin()
    if admin_check:
        return admin_check
    payload = request.get_json(silent=True) or {}
    date_from = payload.get("from")
    date_to = payload.get("to")
    report = run_ai_report(date_from=date_from, date_to=date_to, fuente="manual")
    return jsonify(report)


@app.route("/api/ia/reportes/ultimo", methods=["GET"])
def api_ia_last_report():
    if not check_login():
        return jsonify({"error": "No autenticado"}), 401
    report = get_latest_ai_report()
    if not report:
        return jsonify({"error": "Aun no se han generado reportes IA."}), 404
    return jsonify(report)


def get_latest_ai_report() -> Optional[Dict[str, Any]]:
    conn = None
    try:
        conn = get_db_conn()
        cur = conn.cursor(dictionary=True)
        ensure_ai_logs_table(cur)
        cur.execute(
            """
            SELECT payload_json
            FROM tabla_logs_ia
            ORDER BY fecha_ejecucion DESC, id DESC
            LIMIT 1
            """
        )
        row = cur.fetchone()
        if not row:
            return None
        payload_raw = row.get("payload_json")
        if not payload_raw:
            return None
        return json.loads(payload_raw)
    except Exception as exc:
        print(f"[ia] error obteniendo reporte IA: {exc}")
        return None
    finally:
        if conn:
            conn.close()


def build_ai_report_payload(
    date_from: Optional[str] = None, date_to: Optional[str] = None
) -> Dict[str, Any]:
    sales_df = load_sales_dataframe_for_ai(date_from=date_from, date_to=date_to)
    inventory_rows = fetch_inventory_snapshot()
    today = datetime.now(BOGOTA_TZ).replace(tzinfo=None)
    report = generate_ai_report(sales_df, inventory_rows, today=today)
    report["fuente_datos"] = {
        "ventas": (
            "mysql" if sales_df is not None and not sales_df.empty else "backup_csv"
        ),
        "inventario": "mysql",
        "rango": {"desde": date_from, "hasta": date_to},
    }
    return report


def parse_iso_date(value: Optional[str], label: str) -> Optional[datetime]:
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(
            f"Fecha {label} inválida: '{raw}'. Usa YYYY-MM-DD."
        ) from exc


def filter_sales_by_period(
    sales_df: Optional[pd.DataFrame],
    date_from: Optional[str],
    date_to: Optional[str],
) -> Optional[pd.DataFrame]:
    if sales_df is None or sales_df.empty or not date_from or not date_to:
        return sales_df
    df = sales_df.copy()
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    elif "date" in df.columns:
        df["timestamp"] = pd.to_datetime(df["date"], errors="coerce")
    else:
        return pd.DataFrame()
    start = datetime.strptime(date_from, "%Y-%m-%d")
    end = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
    return df[(df["timestamp"] >= start) & (df["timestamp"] < end)].copy()


def classify_model_quality(mape: Any) -> str:
    try:
        value = float(mape)
    except (TypeError, ValueError):
        return "estimada"
    if value <= 20:
        return "alta"
    if value <= 35:
        return "media"
    return "baja"


def estimate_model_confidence(strategy: str, quality: str, mape: Any) -> float:
    if quality == "alta":
        return 85.0
    if quality == "media":
        return 65.0
    if quality == "baja":
        return 35.0
    if strategy == "modelo_entrenado":
        return 60.0
    if strategy == "regla_stock_minimo":
        return 30.0
    try:
        value = float(mape)
        return max(0.0, min(100.0, 100.0 - value))
    except (TypeError, ValueError):
        return 45.0


def normalize_risk_level(stock: int, min_stock: int, cover_days: Optional[float]) -> str:
    if cover_days is not None:
        if stock <= 0 or cover_days <= 3:
            return "critico"
        if stock <= min_stock or cover_days <= 7:
            return "alerta"
        return "estable"
    if stock <= min_stock and min_stock > 0:
        return "alerta"
    return "sin_dato"


def build_demand_forecast_rows(
    *,
    inventory_rows: List[Dict[str, Any]],
    report: Dict[str, Any],
    horizon_days: int,
    latest_reference: datetime,
    limit: int,
) -> List[Dict[str, Any]]:
    prediction_map = report.get("predicciones_demanda") or {}
    rotation_map = {
        str(item.get("producto") or "").strip(): item
        for item in (report.get("productos_alta_rotacion") or [])
        if (item or {}).get("producto")
    }
    rows: List[Dict[str, Any]] = []
    reference_date = latest_reference
    current_reference = bogota_now_naive()
    if current_reference > reference_date:
        reference_date = current_reference
    for raw in inventory_rows:
        normalized_raw = serialize_product_row(raw)
        product = str(normalized_raw.get("nombre") or "").strip()
        if not product:
            continue
        try:
            stock = int(normalized_raw.get("stock") or 0)
        except (TypeError, ValueError):
            stock = 0
        try:
            min_stock = int(normalized_raw.get("min_stock") or 0)
        except (TypeError, ValueError):
            min_stock = 0
        category = str(normalized_raw.get("categoria") or "").strip()
        image_url = (
            str(
                normalized_raw.get("imagen_url")
                or normalized_raw.get("image_url")
                or normalized_raw.get("image")
                or ""
            ).strip()
            or None
        )
        predicted_total = None
        predicted_info = prediction_map.get(product)
        if isinstance(predicted_info, dict):
            try:
                predicted_total = max(
                    float(predicted_info.get("predicted_demand") or 0.0), 0.0
                )
            except (TypeError, ValueError):
                predicted_total = None
        if predicted_total is None:
            rotation = rotation_map.get(product) or {}
            try:
                daily = float(rotation.get("promedio_diario") or 0.0)
            except (TypeError, ValueError):
                daily = 0.0
            predicted_total = (
                round(daily * horizon_days, 2) if daily > 0 else None
            )
        daily_demand = (
            predicted_total / horizon_days
            if predicted_total is not None and horizon_days > 0
            else None
        )
        cover_days = None
        if daily_demand is not None and daily_demand > 0:
            cover_days = round(stock / daily_demand, 1) if stock > 0 else 0.0
        risk_level = normalize_risk_level(stock, min_stock, cover_days)
        suggested = 0
        if daily_demand is not None and daily_demand > 0:
            target_stock = max(min_stock * 2, int(math.ceil(daily_demand * horizon_days)))
            suggested = max(target_stock - stock, 0)
        elif stock <= min_stock:
            suggested = max((min_stock * 2) - stock, 0)
        runout_date = None
        if cover_days is not None:
            runout_date = (
                reference_date + timedelta(days=max(cover_days, 0.0))
            ).date().isoformat()
        rows.append(
            {
                "product": product,
                "category": category or "Sin categoria",
                "predicted_demand": round(float(predicted_total or 0.0), 2),
                "daily_demand": round(float(daily_demand or 0.0), 2),
                "predicted_qty": round(float(predicted_total or 0.0), 2),
                "predicted_daily": round(float(daily_demand or 0.0), 2),
                "stock": stock,
                "min_stock": min_stock,
                "cover_days": cover_days,
                "risk_level": risk_level,
                "runout_date": runout_date,
                "suggested_purchase": int(suggested),
                "image_url": image_url,
            }
        )
    risk_priority = {"critico": 0, "alerta": 1, "estable": 2, "sin_dato": 3}
    rows.sort(
        key=lambda item: (
            risk_priority.get(str(item.get("risk_level")), 9),
            -int(item.get("suggested_purchase") or 0),
            float(item.get("cover_days") or 9999),
            str(item.get("product") or ""),
        )
    )
    return rows[: max(1, limit)]


@app.route("/api/ia/pronostico-demanda", methods=["GET"])
def api_ia_forecast():
    permission_check = require_permission("statistics_view")
    if permission_check:
        return permission_check
    date_from_raw = (request.args.get("from") or "").strip()
    date_to_raw = (request.args.get("to") or "").strip()
    if bool(date_from_raw) ^ bool(date_to_raw):
        return (
            jsonify(
                {
                    "success": False,
                    "error": "Para usar filtro de fechas debes enviar from y to.",
                }
            ),
            400,
        )
    try:
        date_from = parse_iso_date(date_from_raw, "from")
        date_to = parse_iso_date(date_to_raw, "to")
        if date_from and date_to and date_from > date_to:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "El rango de fechas es inválido.",
                    }
                ),
                400,
            )
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    try:
        horizon = int(request.args.get("horizon", "14"))
    except (TypeError, ValueError):
        horizon = -1
    if horizon < 3 or horizon > 90:
        return (
            jsonify(
                {
                    "success": False,
                    "error": "El parametro horizon debe estar entre 3 y 90 dias.",
                }
            ),
            400,
        )
    try:
        limit = int(request.args.get("limit", "30"))
    except (TypeError, ValueError):
        limit = 30
    limit = max(1, min(limit, 200))
    date_from_str = date_from.strftime("%Y-%m-%d") if date_from else None
    date_to_str = date_to.strftime("%Y-%m-%d") if date_to else None
    sales_data = load_sales_dataframe_for_ai(date_from_str, date_to_str)
    sales_period = filter_sales_by_period(sales_data, date_from_str, date_to_str)
    fallback_all_time = False
    inventory_only = False
    if (sales_period is None or sales_period.empty) and (date_from_str and date_to_str):
        fallback_all_time = True
        sales_period = load_sales_dataframe_for_ai()
    if sales_period is None:
        sales_period = pd.DataFrame()
    if sales_period.empty:
        inventory_only = True
    inventory_rows = fetch_inventory_snapshot()
    report = generate_ai_report(
        sales_period,
        inventory_rows,
        today=datetime.now(BOGOTA_TZ).replace(tzinfo=None),
        config=AIEngineConfig(horizon_days=horizon),
    )
    metadata = (report.get("metadata") or {}).get("modelo_demanda") or {}
    strategy = str(metadata.get("estrategia") or "heuristica_promedio")
    mape = metadata.get("mape")
    quality = classify_model_quality(mape)
    confidence = estimate_model_confidence(strategy, quality, mape)
    latest_reference = datetime.now(BOGOTA_TZ).replace(tzinfo=None)
    if not sales_period.empty:
        if "timestamp" in sales_period.columns:
            ts = pd.to_datetime(sales_period["timestamp"], errors="coerce").max()
        elif "date" in sales_period.columns:
            ts = pd.to_datetime(sales_period["date"], errors="coerce").max()
        else:
            ts = None
        if ts is not None and pd.notna(ts):
            latest_reference = (
                ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts
            )
    forecast_rows = build_demand_forecast_rows(
        inventory_rows=inventory_rows,
        report=report,
        horizon_days=horizon,
        latest_reference=latest_reference,
        limit=limit,
    )
    critical = sum(1 for item in forecast_rows if item.get("risk_level") == "critico")
    warning = sum(1 for item in forecast_rows if item.get("risk_level") == "alerta")
    coverage_values = [
        float(item["cover_days"])
        for item in forecast_rows
        if item.get("cover_days") is not None
    ]
    avg_cover = (
        round(sum(coverage_values) / len(coverage_values), 1)
        if coverage_values
        else None
    )
    return jsonify(
        {
            "success": True,
            "model": {
                "strategy": strategy,
                "quality": quality,
                "confidence": confidence,
                "mape": mape,
                "horizon_days": horizon,
            },
            "summary": {
                "products": len(forecast_rows),
                "critical": critical,
                "warning": warning,
                "avg_cover_days": avg_cover,
            },
            "period": {
                "from": date_from_str,
                "to": date_to_str,
                "fallback_all_time": fallback_all_time,
                "inventory_only": inventory_only,
            },
            "config": {"horizon_days": horizon, "limit": limit},
            "forecast": forecast_rows,
        }
    )


def run_ai_report(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    fuente: str = "manual",
) -> Dict[str, Any]:
    payload = build_ai_report_payload(date_from=date_from, date_to=date_to)
    try:
        store_ai_report_log(payload, fuente=fuente)
    except Exception as exc:
        print(f"[ia] no se pudo registrar el reporte IA: {exc}")
    return payload


def compute_chat_insights(sales_df: pd.DataFrame) -> Dict[str, Any]:
    return chat_response_utils.compute_chat_insights(
        sales_df,
        inventory_rows=fetch_inventory_snapshot(),
    )


def generate_chat_response(
    question: str, sales_df: pd.DataFrame
) -> Tuple[str, Dict[str, Any]]:
    inventory_rows = fetch_inventory_snapshot()
    return chat_response_utils.generate_chat_response(
        question,
        sales_df,
        inventory_rows=inventory_rows,
    )


@app.route("/api/ia/chat", methods=["POST"])
def api_ia_chat():
    login_check = require_login()
    if login_check:
        return login_check
    permission_check = require_permission("ai_chat")
    if permission_check:
        return permission_check
    payload = request.get_json(force=True) or {}
    question = (payload.get("question") or "").strip()
    if not question:
        return jsonify({"error": "La pregunta es obligatoria."}), 400
    sales_data = load_sales_dataframe_for_ai()
    if sales_data is None or sales_data.empty:
        return jsonify({"error": "No hay datos de ventas para analizar."}), 404
    try:
        answer, insights = generate_chat_response(question, sales_data)
    except Exception as exc:
        print(f"[ia-chat] error generando respuesta: {exc}")
        return jsonify({"error": "No se pudo generar la respuesta."}), 500
    return jsonify({"answer": answer, "insights": insights})


@app.route("/api/ia/recomendaciones", methods=["GET"])
def api_recomendaciones():
    login_check = require_login()
    if login_check:
        return login_check
    date_from = request.args.get("from")
    date_to = request.args.get("to")
    for label, val in (("from", date_from), ("to", date_to)):
        if val:
            try:
                datetime.strptime(val, "%Y-%m-%d")
            except ValueError:
                return (
                    jsonify(
                        {"error": f"Fecha {label} inválida: '{val}'. Usa YYYY-MM-DD."}
                    ),
                    400,
                )
    sales_data = load_sales_dataframe_for_ai(date_from, date_to)
    if sales_data is None or sales_data.empty:
        return jsonify({"error": "No hay datos de ventas para analizar."}), 404
    inventory_rows = fetch_inventory_snapshot()
    report = generate_ai_report(
        sales_data,
        inventory_rows,
        today=datetime.now(BOGOTA_TZ).replace(tzinfo=None),
    )
    top_rotation = report.get("productos_alta_rotacion") or []
    top_product = {}
    if top_rotation:
        top_product = {
            "product": top_rotation[0].get("producto"),
            "qty": int(top_rotation[0].get("unidades_periodo") or 0),
            "revenue": None,
        }
    payload: Dict[str, Any] = dict(report)
    payload.setdefault("top_product", top_product)
    payload.setdefault("offer_suggestions", [])
    payload.setdefault("combo_suggestions", [])
    return jsonify(payload)


@app.route("/")
def serve_index():
    frontend_dir = get_frontend_dir()
    index_path = frontend_dir / "index.html"
    html = index_path.read_text(encoding="utf-8")
    html = html.replace(
        FRONTEND_ASSET_VERSION_TOKEN, get_frontend_asset_version()
    )
    resp = app.response_class(html, mimetype="text/html")
    # recommend short caching for HTML (validate frequently)
    resp.cache_control.no_cache = False
    resp.headers["Cache-Control"] = "no-cache"
    return resp


@app.route("/<path:path>")
def serve_static(path: str):
    static_dir = get_frontend_dir()
    full_path = static_dir / path
    if full_path.exists():
        # Siempre servimos el archivo fuente para evitar inconsistencias por
        # assets .gz obsoletos generados en sesiones previas.
        resp = send_from_directory(str(static_dir), path)
        # set cache for common static types
        if path.endswith(
            (".js", ".css", ".woff", ".woff2", ".svg", ".png", ".jpg", ".jpeg")
        ):
            resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return resp
    return redirect("/")


def run_with_mysql(
    date_from: Optional[str] = None, date_to: Optional[str] = None
) -> Optional[pd.DataFrame]:
    print("[cli] Cargando datos desde MySQL...")
    df = load_sales_from_db(DB_CONFIG, date_from=date_from, date_to=date_to)
    if df is None or df.empty:
        print("[cli] No se encontraron ventas en el rango indicado.")
        return None
    print(f"[cli] Ventas cargadas: {len(df)} filas")
    return df


def run_with_csv(csv_path: str = "data/sales_data.csv") -> Optional[pd.DataFrame]:
    print(f"[cli] Cargando datos desde CSV: {csv_path}")
    if not os.path.exists(csv_path):
        print("[cli] CSV no encontrado.")
        return None
    try:
        df = load_sales_data(csv_path)
        print(f"[cli] Ventas cargadas (CSV): {len(df)} filas")
        return df
    except Exception as exc:
        print(f"[cli] Error cargando CSV: {exc}")
        return None


def main_setup_users_cli() -> int:
    parser = argparse.ArgumentParser(
        prog="setup_users",
        description="Configura/actualiza usuarios base del sistema.",
    )
    parser.add_argument("--admin-user", default="admin")
    parser.add_argument("--seller-user", default="vendedor")
    parser.add_argument("--admin-pass", default=DEFAULT_ADMIN_PASSWORD)
    parser.add_argument("--seller-pass", default=DEFAULT_VENDOR_PASSWORD)
    parser.add_argument("--admin-name", default="Administrador")
    parser.add_argument("--seller-name", default="Vendedor")
    args = parser.parse_args(sys.argv[2:])
    admin_user = (args.admin_user or "").strip().lower()
    seller_user = (args.seller_user or "").strip().lower()
    if not admin_user or not seller_user:
        print("[setup_users] Debes indicar admin-user y seller-user.")
        return 1
    if admin_user == seller_user:
        print("[setup_users] admin-user y seller-user deben ser diferentes.")
        return 1
    conn = None
    try:
        conn = get_db_conn()
        admin_result = reset_user_password(
            conn,
            admin_user,
            args.admin_pass,
            role="admin",
            name=args.admin_name,
            activate=True,
        )
        seller_result = reset_user_password(
            conn,
            seller_user,
            args.seller_pass,
            role="vendedor",
            name=args.seller_name,
            activate=True,
        )
        print(
            "[setup_users] OK admin={admin} vendedor={seller}".format(
                admin=admin_result.get("username"),
                seller=seller_result.get("username"),
            )
        )
        return 0
    except ValueError as exc:
        print(f"[setup_users] ERROR validacion: {exc}")
        return 1
    except Exception as exc:
        print(f"[setup_users] ERROR: {exc}")
        return 1
    finally:
        if conn:
            conn.close()


def main_cli():
    import sys

    date_from = sys.argv[2] if len(sys.argv) > 2 else None
    date_to = sys.argv[3] if len(sys.argv) > 3 else None
    for label, val in (("from", date_from), ("to", date_to)):
        if val:
            try:
                datetime.strptime(val, "%Y-%m-%d")
            except ValueError:
                print(f"[cli] Fecha {label} inválida: '{val}'. Usa YYYY-MM-DD.")
                return
    sales_data = run_with_mysql(date_from, date_to)
    if sales_data is None or sales_data.empty:
        sales_data = run_with_csv()
    if sales_data is None or sales_data.empty:
        print("[cli] No hay datos de ventas para analizar.")
        return
    print("[cli] Ejecutando recomendaciones...")
    recommender = Recommender(sales_data)
    recommendations = recommender.analyze_sales()
    notifier = Notifier()
    top_product = safe_get(recommendations, "top_product")
    if top_product:
        notifier.send_top_product_notification(top_product)
    offer_suggestions = safe_get(recommendations, "offer_suggestions", [])
    if offer_suggestions:
        notifier.send_offer_suggestions(offer_suggestions)
    combo_suggestions = safe_get(recommendations, "combo_suggestions", [])
    if combo_suggestions:
        notifier.send_combo_suggestions(combo_suggestions)
    restock_alerts = safe_get(recommendations, "restock_alerts", [])
    if restock_alerts:
        notifier.send_restock_alerts(restock_alerts)
    print("\n===== RESUMEN =====")
    print(f"Producto más vendido: {top_product}")
    print(f"Sugerencias de ofertas ({len(offer_suggestions)}): {offer_suggestions}")
    print(f"Combos sugeridos ({len(combo_suggestions)}): {combo_suggestions}")
    print(f"Reposición sugerida ({len(restock_alerts)}): {restock_alerts}")


if __name__ == "__main__":
    import sys

    cmd = sys.argv[1] if len(sys.argv) > 1 else None
    if cmd == "cli":
        main_cli()
    elif cmd == "cleanup_sessions":
        stats = perform_sessions_cleanup()
        print(f"[session] limpieza completada: {stats['revoked']} sesiones revocadas.")
    elif cmd == "bootstrap":
        stats = bootstrap_database()
        print(
            "[bootstrap] tablas listas. Usuarios: {usuarios}, Productos: {productos}, Ventas: {ventas}, Migraciones: {migraciones}".format(
                usuarios=stats.get("usuarios", 0),
                productos=stats.get("productos", 0),
                ventas=stats.get("ventas", 0),
                migraciones=stats.get("migraciones", 0),
            )
        )
    elif cmd == "migrate":
        ok = ensure_runtime_schema(force=True)
        if ok:
            print("[schema] migraciones aplicadas correctamente.")
        else:
            print("[schema] no se pudieron aplicar migraciones.")
    elif cmd == "unlock_admin":
        password_arg = sys.argv[2] if len(sys.argv) > 2 else ""
        ok, message = unlock_admin_password(password_arg)
        prefix = "[auth]" if ok else "[auth] ERROR"
        print(f"{prefix} {message}")
    elif cmd == "ai_report":
        report = run_ai_report(fuente="cli")
        print(json.dumps(report, indent=2, ensure_ascii=False))
    elif cmd == "backup":
        path = perform_backup(reason="manual-cli")
        if path:
            print(f"[backup] respaldo generado en {path}")
        else:
            print("[backup] no se pudo generar el respaldo.")
    elif cmd == "setup_users":
        raise SystemExit(main_setup_users_cli())
    else:
        port = int(os.environ.get("PORT", "5000"))
        debug = os.environ.get("FLASK_DEBUG", "0") == "1"
        ensure_runtime_schema()
        initialize_backup_scheduler()
        app.run(debug=debug, host="0.0.0.0", port=port)
