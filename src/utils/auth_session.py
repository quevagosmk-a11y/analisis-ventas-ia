from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict


def build_session_user_payload(
    session_store,
    *,
    role_display_name: Callable[[Any], str],
    normalize_permissions_map: Callable[..., Dict[str, bool]],
    default_idle_minutes: int,
    warning_seconds: int,
    price_change_max_ratio: float,
    price_force_reason_min_length: int,
) -> Dict[str, Any]:
    return {
        "id": session_store["user_id"],
        "username": session_store["username"],
        "role": session_store["role"],
        "name": session_store.get("name", session_store["username"]),
        "role_name": session_store.get("role_name")
        or role_display_name(session_store.get("role")),
        "permissions": session_store.get("permissions")
        or normalize_permissions_map({}, role=session_store.get("role")),
        "login_at": session_store.get("login_at"),
        "last_activity": session_store.get("last_activity"),
        "idle_minutes": session_store.get("idle_minutes", default_idle_minutes),
        "warning_seconds": warning_seconds,
        "session_token": session_store.get("session_token"),
        "session_expires_at": session_store.get("expires_at"),
        "session_expires_at_utc": session_store.get("expires_at_utc"),
        "price_change_max_ratio": price_change_max_ratio,
        "price_force_reason_min_length": price_force_reason_min_length,
    }


def sync_session_expiration_fields(
    session_store,
    state,
    *,
    bogota_isoformat: Callable[[Any], Any],
) -> None:
    if state.expires_at:
        session_store["expires_at"] = bogota_isoformat(state.expires_at)
        session_store["expires_at_utc"] = state.expires_at.isoformat()
    else:
        session_store.pop("expires_at", None)
        session_store.pop("expires_at_utc", None)


def finalize_login_session(
    conn,
    user_payload: Dict[str, Any],
    *,
    session_store,
    server_boot_id: str,
    bogota_now_naive: Callable[[], Any],
    normalize_permissions_map: Callable[..., Dict[str, bool]],
    role_display_name: Callable[[Any], str],
    apply_role_session_defaults: Callable[[Dict[str, Any]], None],
    generate_session_token: Callable[[], str],
    store_session_token: Callable[..., Any],
    get_session_state: Callable[[str], Any],
    sync_session_expiration_fields: Callable[[Any], None],
    build_session_user_payload: Callable[[], Dict[str, Any]],
    warning_seconds: int,
    user_agent: Any,
) -> Dict[str, Any]:
    session_store.clear()
    session_store.permanent = True
    session_store["user_id"] = user_payload["id"]
    session_store["username"] = user_payload["username"]
    session_store["role"] = user_payload["role"]
    session_store["name"] = user_payload["name"]
    session_store["role_name"] = user_payload.get("role_name") or role_display_name(
        user_payload["role"]
    )
    session_store["server_boot_id"] = server_boot_id
    session_store["permissions"] = normalize_permissions_map(
        user_payload.get("permissions") or {},
        role=user_payload["role"],
    )
    now_local = bogota_now_naive()
    session_store["login_at"] = now_local.isoformat()
    session_store["last_activity"] = now_local.isoformat()
    apply_role_session_defaults(user_payload)
    token = generate_session_token()
    session_store["session_token"] = token
    store_session_token(
        conn,
        token,
        user_payload["id"],
        user_payload["role"],
        session_store["idle_minutes"],
        user_agent,
    )
    state = get_session_state(token)
    sync_session_expiration_fields(state)
    session_user = build_session_user_payload()
    return {
        "success": True,
        "user": session_user,
        "session_token": token,
        "idle_minutes": session_store["idle_minutes"],
        "warning_seconds": warning_seconds,
    }


def build_session_status_payload(
    session_store,
    state,
    *,
    parse_session_datetime: Callable[[Any], Any],
    bogota_now_naive: Callable[[], Any],
    bogota_isoformat: Callable[[Any], Any],
    default_idle_minutes: int,
    warning_seconds: int,
) -> Dict[str, Any]:
    idle_minutes = session_store.get("idle_minutes", default_idle_minutes)
    seconds_left = idle_minutes * 60
    if state.expires_at:
        delta = state.expires_at - datetime.now(timezone.utc)
        seconds_left = max(0, int(delta.total_seconds()))
    else:
        last_activity_raw = session_store.get("last_activity")
        if last_activity_raw:
            last = parse_session_datetime(last_activity_raw)
            if last is not None:
                delta = timedelta(minutes=idle_minutes) - (bogota_now_naive() - last)
                seconds_left = max(0, int(delta.total_seconds()))
            else:
                seconds_left = idle_minutes * 60
    return {
        "active": True,
        "seconds_left": seconds_left,
        "warning_seconds": warning_seconds,
        "expires_at": bogota_isoformat(state.expires_at),
        "expires_at_utc": state.expires_at.isoformat() if state.expires_at else None,
        "login_at": session_store.get("login_at"),
        "last_activity": session_store.get("last_activity"),
    }


def build_session_ping_response(
    session_store,
    state,
    *,
    bogota_now_naive: Callable[[], Any],
    sync_session_expiration_fields: Callable[[Any], None],
) -> Dict[str, Any]:
    session_store["last_activity"] = bogota_now_naive().isoformat()
    sync_session_expiration_fields(state)
    return {
        "success": True,
        "expires_at": session_store.get("expires_at"),
        "expires_at_utc": session_store.get("expires_at_utc"),
    }
