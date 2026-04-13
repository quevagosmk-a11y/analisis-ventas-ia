from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Optional


def build_login_attempt_key(username: str, client_ip: str) -> str:
    return f"{str(username or '').strip().lower()}|{str(client_ip or '').strip().lower()}"


def prune_login_throttle_state(
    login_attempts: Dict[str, list[datetime]],
    login_lockouts: Dict[str, datetime],
    *,
    now: Optional[datetime] = None,
    login_attempt_window_seconds: int,
) -> None:
    reference = now or datetime.now(timezone.utc)
    cutoff = reference - timedelta(seconds=login_attempt_window_seconds)
    for key, attempts in list(login_attempts.items()):
        recent = [item for item in attempts if item >= cutoff]
        if recent:
            login_attempts[key] = recent
        else:
            login_attempts.pop(key, None)
    for key, locked_until in list(login_lockouts.items()):
        if locked_until <= reference:
            login_lockouts.pop(key, None)


def get_login_throttle_seconds_left(
    username: str,
    client_ip: str,
    *,
    login_attempt_lock: Any,
    login_lockouts: Dict[str, datetime],
    build_login_attempt_key: Callable[[str, str], str],
    prune_login_throttle_state: Callable[[Optional[datetime]], None],
) -> int:
    key = build_login_attempt_key(username, client_ip)
    now = datetime.now(timezone.utc)
    with login_attempt_lock:
        prune_login_throttle_state(now)
        locked_until = login_lockouts.get(key)
        if not locked_until:
            return 0
        return max(0, int((locked_until - now).total_seconds()))


def register_failed_login_attempt(
    username: str,
    client_ip: str,
    *,
    login_attempt_lock: Any,
    login_attempts: Dict[str, list[datetime]],
    login_lockouts: Dict[str, datetime],
    build_login_attempt_key: Callable[[str, str], str],
    prune_login_throttle_state: Callable[[Optional[datetime]], None],
    login_attempt_limit: int,
    login_lockout_seconds: int,
) -> int:
    key = build_login_attempt_key(username, client_ip)
    now = datetime.now(timezone.utc)
    with login_attempt_lock:
        prune_login_throttle_state(now)
        attempts = login_attempts.setdefault(key, [])
        attempts.append(now)
        if len(attempts) >= login_attempt_limit:
            locked_until = now + timedelta(seconds=login_lockout_seconds)
            login_lockouts[key] = locked_until
            return int((locked_until - now).total_seconds())
        return 0


def clear_login_attempts(
    username: str,
    client_ip: str,
    *,
    login_attempt_lock: Any,
    login_attempts: Dict[str, list[datetime]],
    login_lockouts: Dict[str, datetime],
    build_login_attempt_key: Callable[[str, str], str],
) -> None:
    key = build_login_attempt_key(username, client_ip)
    with login_attempt_lock:
        login_attempts.pop(key, None)
        login_lockouts.pop(key, None)


def is_session_bound_to_current_boot(
    session_store,
    *,
    server_boot_id: str,
    testing_enabled: bool,
) -> bool:
    if "user_id" not in session_store:
        return False
    boot_id = str(session_store.get("server_boot_id") or "").strip()
    if not boot_id:
        return bool(testing_enabled)
    return boot_id == server_boot_id


def revoke_and_clear_session(
    session_store,
    *,
    revoke_session_token: Callable[[Any], None],
) -> None:
    revoke_session_token(session_store.get("session_token"))
    session_store.clear()


def check_login(
    session_store,
    *,
    is_session_bound_to_current_boot: Callable[[], bool],
) -> bool:
    return is_session_bound_to_current_boot()


def require_login(
    session_store,
    *,
    check_login: Callable[[], bool],
    jsonify: Callable[[Dict[str, Any]], Any],
):
    if not check_login():
        return jsonify({"error": "No autenticado"}), 401
    return None


def require_admin(
    session_store,
    *,
    check_login: Callable[[], bool],
    jsonify: Callable[[Dict[str, Any]], Any],
):
    if not check_login() or session_store.get("role") != "admin":
        return jsonify({"error": "No autorizado"}), 403
    return None


def get_session_permissions(
    session_store,
    *,
    coerce_user_role: Callable[[Any], str],
    normalize_permissions_map: Callable[..., Dict[str, bool]],
) -> Dict[str, bool]:
    role = coerce_user_role(session_store.get("role") or "vendedor")
    permissions = normalize_permissions_map(
        session_store.get("permissions") or {},
        role=role,
    )
    session_store["permissions"] = permissions
    return permissions


def require_permission(
    permission_key: str,
    *,
    session_store,
    require_login: Callable[[], Any],
    get_session_permissions: Callable[[], Dict[str, bool]],
    jsonify: Callable[[Dict[str, Any]], Any],
):
    login_check = require_login()
    if login_check:
        return login_check
    if session_store.get("role") == "admin":
        return None
    permissions = get_session_permissions()
    if permissions.get(permission_key):
        return None
    return jsonify({"error": "No autorizado"}), 403
