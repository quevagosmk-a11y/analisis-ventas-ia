from __future__ import annotations

from datetime import timedelta
from typing import Any, Callable, Dict, Optional, Tuple


def should_skip_session_enforcement(endpoint: str) -> bool:
    return bool(
        endpoint
        and (
            endpoint.startswith("static")
            or endpoint in {"spec", "swagger_ui", "serve_index", "serve_static"}
            or endpoint.startswith("flasgger.")
        )
    )


def describe_session_failure(
    state,
    *,
    revoked_message: str,
    expired_message: str,
) -> Tuple[str, str]:
    reason_key = "revoked" if state.revoked else "expired"
    return reason_key, revoked_message if state.revoked else expired_message


def read_session_idle_status(
    session_store,
    *,
    bogota_now_naive: Callable[[], Any],
    parse_session_datetime: Callable[[Any], Any],
    default_idle_minutes: int,
) -> Tuple[Any, int, bool]:
    now_local = bogota_now_naive()
    idle_minutes = session_store.get("idle_minutes", default_idle_minutes)
    last_activity = parse_session_datetime(session_store.get("last_activity"))
    expired = bool(
        last_activity and now_local - last_activity > timedelta(minutes=idle_minutes)
    )
    return now_local, idle_minutes, expired


def refresh_active_session(
    session_store,
    state,
    *,
    now_local: Any,
    sync_session_expiration_fields: Callable[[Any], None],
) -> None:
    session_store["last_activity"] = now_local.isoformat()
    sync_session_expiration_fields(state)


def process_login_request(
    payload: Dict[str, Any],
    *,
    get_request_client_ip: Callable[[], str],
    get_login_throttle_seconds_left: Callable[[str, str], int],
    get_db_conn: Callable[[], Any],
    ensure_runtime_schema: Callable[[Any], Any],
    ensure_seed_users: Callable[[Any], None],
    fetch_user_by_credentials: Callable[[Any, str, str], Optional[Dict[str, Any]]],
    register_failed_login_attempt: Callable[[str, str], int],
    clear_login_attempts: Callable[[str, str], None],
    build_user_payload: Callable[[Dict[str, Any]], Dict[str, Any]],
    finalize_login_session: Callable[[Any, Dict[str, Any]], Dict[str, Any]],
    try_record_audit_event: Callable[..., Any],
    print_fn: Callable[[str], None],
) -> Tuple[Dict[str, Any], int]:
    username = (payload.get("username") or "").strip()
    password = payload.get("password") or ""
    client_ip = get_request_client_ip()
    if not username or not password:
        return (
            {"success": False, "error": "Usuario y contraseña obligatorios."},
            400,
        )
    seconds_left = get_login_throttle_seconds_left(username, client_ip)
    if seconds_left > 0:
        return (
            {
                "success": False,
                "error": "Demasiados intentos fallidos. Espera antes de volver a intentar.",
                "seconds_left": seconds_left,
            },
            429,
        )
    try:
        conn = get_db_conn()
        ensure_runtime_schema(conn)
    except Exception as exc:
        print_fn(f"[auth] no se pudo conectar a la BD en login: {exc}")
        return (
            {
                "success": False,
                "error": "No se pudo conectar a la base de datos. Verifica MySQL y credenciales.",
            },
            503,
        )
    try:
        ensure_seed_users(conn)
        user_row = fetch_user_by_credentials(conn, username, password)
        if not user_row:
            lockout = register_failed_login_attempt(username, client_ip)
            try_record_audit_event(
                conn,
                event_type="login_fallido",
                entity_type="sesion",
                entity_id=None,
                description=f'Intento fallido de acceso para "{username}"',
                details={"client_ip": client_ip, "lockout_seconds": lockout},
                actor_username=username,
            )
            if lockout > 0:
                return (
                    {
                        "success": False,
                        "error": "Credenciales invalidas. Se bloqueó temporalmente el acceso por demasiados intentos.",
                        "seconds_left": lockout,
                    },
                    429,
                )
            return {"success": False, "error": "Credenciales invalidas."}, 401
        clear_login_attempts(username, client_ip)
        user_payload = build_user_payload(user_row)
        response_payload = finalize_login_session(conn, user_payload)
        try_record_audit_event(
            conn,
            event_type="login_exitoso",
            entity_type="sesion",
            entity_id=response_payload["user"]["id"],
            description=f'Inicio de sesión para "{response_payload["user"]["username"]}"',
            details={
                "client_ip": client_ip,
                "role": response_payload["user"]["role"],
            },
            actor_user_id=response_payload["user"]["id"],
            actor_username=response_payload["user"]["username"],
        )
        return response_payload, 200
    except Exception as exc:
        try:
            conn.rollback()
        except Exception:
            pass
        print_fn(f"[auth] error en proceso de login: {exc}")
        return (
            {
                "success": False,
                "error": "No se pudo iniciar sesión por un problema de base de datos.",
            },
            503,
        )
    finally:
        conn.close()
