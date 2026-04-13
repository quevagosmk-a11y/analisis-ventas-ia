from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import pymysql
from pymysql.cursors import DictCursor

logger = logging.getLogger(__name__)


class _ConnectionWrapper:
    """
    Pequeño adaptador que replica la interfaz básica de mysql.connector
    usando PyMySQL bajo el capó. Permite seguir usando cursor(dictionary=True).
    """

    def __init__(self, connection: pymysql.Connection):
        self._connection = connection

    def cursor(self, dictionary: bool = False):
        if dictionary:
            return self._connection.cursor(DictCursor)
        return self._connection.cursor()

    def start_transaction(self, *args: Any, **kwargs: Any) -> None:
        """
        Compatibilidad con mysql.connector.

        PyMySQL no expone `start_transaction`, pero sí `begin`. Algunos flujos
        del proyecto usan la API de mysql.connector de forma explícita.
        """
        native = getattr(self._connection, "start_transaction", None)
        if callable(native):
            native(*args, **kwargs)
            return
        begin = getattr(self._connection, "begin", None)
        if callable(begin):
            begin()
            return
        autocommit = getattr(self._connection, "autocommit", None)
        if callable(autocommit):
            autocommit(False)

    def __getattr__(self, item: str) -> Any:
        return getattr(self._connection, item)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if exc_type:
                self._connection.rollback()
            else:
                self._connection.commit()
        finally:
            self._connection.close()

    def close(self):
        self._connection.close()


def _is_local_root_auth_error(config: Dict[str, Any], exc: Exception) -> bool:
    """Detecta error 1045 en root local para intentar fallback sin clave."""
    errno = None
    try:
        if getattr(exc, "args", None):
            errno = int(exc.args[0])
    except Exception:
        errno = None
    if errno != 1045:
        return False
    user = str(config.get("user") or "").strip().lower()
    host = str(config.get("host") or "").strip().lower()
    if user != "root":
        return False
    if host not in {"", "localhost", "127.0.0.1"}:
        return False
    return True


def _local_root_auth_variants(config: Dict[str, Any]) -> list[Dict[str, Any]]:
    """
    Variantes de conexión para entornos locales (XAMPP/WAMP) donde
    `root` puede aceptar solo ciertas combinaciones host/password.
    """
    variants: list[Dict[str, Any]] = []
    for host in ("localhost", "127.0.0.1"):
        # 1) sin password explícito
        cfg_no_password = dict(config)
        cfg_no_password["host"] = host
        cfg_no_password.pop("password", None)
        variants.append(cfg_no_password)
        # 2) password vacío explícito
        cfg_empty_password = dict(config)
        cfg_empty_password["host"] = host
        cfg_empty_password["password"] = ""
        variants.append(cfg_empty_password)
    # deduplicar
    deduped: list[Dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for cfg in variants:
        signature = (
            cfg.get("host"),
            cfg.get("user"),
            cfg.get("password", "__missing__"),
            cfg.get("database"),
            cfg.get("port"),
        )
        if signature in seen:
            continue
        seen.add(signature)
        deduped.append(cfg)
    return deduped


def connect(**config: Any) -> _ConnectionWrapper:
    """
    Devuelve una conexión compatible con mysql.connector usando PyMySQL
    (evita los fallos nativos que estaban ocurriendo con mysql-connector-python).
    """
    base_config = dict(config)
    try:
        conn = pymysql.connect(charset="utf8mb4", autocommit=False, **base_config)
    except pymysql.err.OperationalError as exc:
        if not _is_local_root_auth_error(base_config, exc):
            raise
        logger.warning(
            "Auth MySQL falló para root local; reintentando variantes locales."
        )
        last_exc: Optional[Exception] = exc
        for retry_config in _local_root_auth_variants(base_config):
            try:
                conn = pymysql.connect(
                    charset="utf8mb4", autocommit=False, **retry_config
                )
                break
            except pymysql.err.OperationalError as retry_exc:
                last_exc = retry_exc
        else:
            raise last_exc  # type: ignore[misc]
    return _ConnectionWrapper(conn)


def ping(config: Dict[str, Any], *, timeout: Optional[int] = None) -> bool:
    base_config = dict(config)
    try:
        conn = pymysql.connect(
            charset="utf8mb4",
            autocommit=True,
            connect_timeout=timeout or 5,
            **base_config,
        )
        conn.close()
        return True
    except pymysql.err.OperationalError as exc:
        if not _is_local_root_auth_error(base_config, exc):
            logger.debug("ping mysql failed: %s", exc)
            return False
        for retry_config in _local_root_auth_variants(base_config):
            try:
                conn = pymysql.connect(
                    charset="utf8mb4",
                    autocommit=True,
                    connect_timeout=timeout or 5,
                    **retry_config,
                )
                conn.close()
                return True
            except Exception as retry_exc:  # pragma: no cover - diagnostico manual
                logger.debug("ping mysql fallback failed: %s", retry_exc)
        return False
    except Exception as exc:  # pragma: no cover - diagnostico manual
        logger.debug("ping mysql failed: %s", exc)
        return False
