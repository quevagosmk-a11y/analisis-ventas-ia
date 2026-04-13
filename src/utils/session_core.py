from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any, Callable, Dict, NamedTuple, Optional


class SessionState(NamedTuple):
    ok: bool
    revoked: bool
    expired: bool
    expires_at: Optional[datetime]


def cleanup_expired_sessions(cur, conn, *, commit: bool = True) -> int:
    try:
        cur.execute(
            """
            UPDATE sesiones_activas
            SET revoked=1
            WHERE revoked=0 AND expires_at < UTC_TIMESTAMP()
            """
        )
        revoked = getattr(cur, "rowcount", 0) or 0
        if commit and revoked:
            conn.commit()
        return revoked
    except Exception as exc:
        print(f"[session] error limpiando sesiones vencidas: {exc}")
        try:
            conn.rollback()
        except Exception:
            pass
        return 0


def perform_sessions_cleanup(
    *,
    get_db_conn: Callable[[], Any],
    ensure_session_table: Callable[[Any], None],
    conn: Optional[Any] = None,
) -> Dict[str, int]:
    owns_connection = conn is None
    stats = {"revoked": 0}
    local_conn = conn or get_db_conn()
    cur = None
    try:
        cur = local_conn.cursor()
        ensure_session_table(cur)
        revoked = cleanup_expired_sessions(cur, local_conn, commit=True)
        stats["revoked"] = revoked
        return stats
    finally:
        if cur:
            try:
                cur.close()
            except Exception:
                pass
        if owns_connection and local_conn:
            local_conn.close()


def get_session_state(
    token: Optional[str],
    *,
    get_db_conn: Callable[[], Any],
    ensure_session_table: Callable[[Any], None],
    idle_minutes: Optional[int] = None,
    refresh: bool = False,
) -> SessionState:
    if not token:
        return SessionState(False, False, True, None)
    conn = None
    try:
        conn = get_db_conn()
        cur = conn.cursor(dictionary=True)
        ensure_session_table(cur)
        cleanup_expired_sessions(cur, conn)
        cur.execute(
            """
            SELECT revoked, expires_at
            FROM sesiones_activas
            WHERE token=%s
            """,
            (token,),
        )
        row = cur.fetchone()
        if not row:
            return SessionState(False, False, True, None)
        revoked = bool(row.get("revoked"))
        expires_at = row.get("expires_at")
        if isinstance(expires_at, datetime) and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        now_utc = datetime.now(timezone.utc)
        expired = bool(expires_at and expires_at <= now_utc)
        if revoked or expired:
            if expired and not revoked:
                try:
                    cur.execute(
                        "UPDATE sesiones_activas SET revoked=1 WHERE token=%s", (token,)
                    )
                    conn.commit()
                except Exception as mark_exc:
                    print(f"[session] error marcando sesion expirada: {mark_exc}")
                    conn.rollback()
            return SessionState(False, revoked, expired, expires_at)
        if refresh and idle_minutes is not None:
            cur.execute(
                """
                UPDATE sesiones_activas
                SET last_activity = UTC_TIMESTAMP(),
                    expires_at = DATE_ADD(UTC_TIMESTAMP(), INTERVAL %s MINUTE)
                WHERE token=%s
                """,
                (idle_minutes, token),
            )
            conn.commit()
            cur.execute(
                "SELECT expires_at FROM sesiones_activas WHERE token=%s", (token,)
            )
            refreshed = cur.fetchone()
            refreshed_exp = refreshed.get("expires_at") if refreshed else None
            if isinstance(refreshed_exp, datetime) and refreshed_exp.tzinfo is None:
                refreshed_exp = refreshed_exp.replace(tzinfo=timezone.utc)
            if refreshed_exp:
                expires_at = refreshed_exp
        return SessionState(True, False, False, expires_at)
    except Exception as exc:
        print(f"[session] error verificando token: {exc}")
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        return SessionState(True, False, False, None)
    finally:
        if conn:
            conn.close()


def store_session_token(
    conn,
    token: str,
    user_id: int,
    role: str,
    idle_minutes: int,
    *,
    ensure_session_table: Callable[[Any], None],
    client_info: Optional[str] = None,
) -> None:
    cur = conn.cursor()
    ensure_session_table(cur)
    cleanup_expired_sessions(cur, conn)
    cur.execute(
        """
        INSERT INTO sesiones_activas (token, user_id, role, created_at, last_activity, expires_at, revoked, client_info)
        VALUES (%s, %s, %s, UTC_TIMESTAMP(), UTC_TIMESTAMP(), DATE_ADD(UTC_TIMESTAMP(), INTERVAL %s MINUTE), 0, %s)
        ON DUPLICATE KEY UPDATE
            user_id = VALUES(user_id),
            role = VALUES(role),
            last_activity = VALUES(last_activity),
            expires_at = VALUES(expires_at),
            revoked = 0,
            client_info = VALUES(client_info)
        """,
        (token, user_id, role, idle_minutes, client_info),
    )
    conn.commit()
    cur.close()


def update_session_activity(
    token: Optional[str],
    idle_minutes: int,
    *,
    get_session_state_fn: Callable[..., SessionState],
) -> bool:
    state = get_session_state_fn(token, idle_minutes=idle_minutes, refresh=True)
    return state.ok


def revoke_session_token(
    token: Optional[str],
    *,
    get_db_conn: Callable[[], Any],
    ensure_session_table: Callable[[Any], None],
) -> None:
    if not token:
        return
    conn = None
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        ensure_session_table(cur)
        cur.execute("UPDATE sesiones_activas SET revoked=1 WHERE token=%s", (token,))
        conn.commit()
    except Exception as exc:
        print(f"[session] error revocando token: {exc}")
    finally:
        if conn:
            conn.close()


def serialize_session_record(
    row: Dict[str, Any],
    current_token: Optional[str],
    *,
    bogota_isoformat: Callable[[Any], Optional[str]],
) -> Dict[str, Any]:
    expires_raw = row.get("expires_at")
    expires_dt: Optional[datetime]
    if isinstance(expires_raw, datetime):
        expires_dt = expires_raw
    elif isinstance(expires_raw, str):
        try:
            expires_dt = datetime.fromisoformat(expires_raw)
        except ValueError:
            expires_dt = None
    else:
        expires_dt = None
    if isinstance(expires_dt, datetime) and expires_dt.tzinfo is None:
        expires_dt = expires_dt.replace(tzinfo=timezone.utc)
    expired = False
    if isinstance(expires_dt, datetime):
        expired = expires_dt <= datetime.now(timezone.utc)
    payload = {
        "token": row.get("token"),
        "user_id": row.get("user_id"),
        "username": row.get("username"),
        "name": row.get("name"),
        "role": row.get("role"),
        "client_info": row.get("client_info"),
        "client": row.get("client_info"),
        "revoked": bool(row.get("revoked")),
        "expired": expired,
        "is_current": row.get("token") == current_token,
        "created_at": bogota_isoformat(row.get("created_at")),
        "last_activity": bogota_isoformat(row.get("last_activity")),
        "expires_at": bogota_isoformat(expires_dt),
        "expires_at_utc": (
            expires_dt.isoformat() if isinstance(expires_dt, datetime) else None
        ),
    }
    if payload["revoked"]:
        payload["status"] = "revoked"
    elif payload["expired"]:
        payload["status"] = "expired"
    else:
        payload["status"] = "active"
    return payload


def get_idle_timeout_for_role(
    role: Optional[str],
    *,
    role_idle_timeouts: Dict[str, int],
    default_idle_timeout: int,
) -> int:
    if role and role in role_idle_timeouts:
        return max(1, role_idle_timeouts[role])
    return default_idle_timeout


def generate_session_token() -> str:
    return secrets.token_hex(32)
