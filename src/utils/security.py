from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
from typing import Optional

PASSWORD_MIN_LENGTH = max(8, int(os.environ.get("PASSWORD_MIN_LENGTH", "8")))
PASSWORD_HASH_SCHEME = "pbkdf2_sha256"
PASSWORD_HASH_ITERATIONS = max(
    120000, int(os.environ.get("PASSWORD_HASH_ITERATIONS", "390000"))
)
DEFAULT_ADMIN_PASSWORD = os.environ.get("DEFAULT_ADMIN_PASSWORD", "Admin2026@")
DEFAULT_VENDOR_PASSWORD = os.environ.get("DEFAULT_VENDOR_PASSWORD", "Vendedor2026@")
PASSWORD_POLICY_MESSAGE = (
    f"La contraseña debe tener al menos {PASSWORD_MIN_LENGTH} caracteres, "
    "incluir una letra mayúscula, una minúscula, un dígito y un símbolo."
)


def _legacy_hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PASSWORD_HASH_ITERATIONS,
    ).hex()
    return f"{PASSWORD_HASH_SCHEME}${PASSWORD_HASH_ITERATIONS}${salt}${digest}"


def _verify_pbkdf2_password(password: str, encoded_hash: str) -> bool:
    try:
        scheme, iter_raw, salt, expected = encoded_hash.split("$", 3)
    except ValueError:
        return False
    if scheme != PASSWORD_HASH_SCHEME:
        return False
    try:
        iterations = int(iter_raw)
    except ValueError:
        return False
    candidate = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        iterations,
    ).hex()
    return hmac.compare_digest(candidate, expected)


def verify_password(password: str, stored_hash: Optional[str]) -> bool:
    if not stored_hash:
        return False
    if stored_hash.startswith(f"{PASSWORD_HASH_SCHEME}$"):
        return _verify_pbkdf2_password(password, stored_hash)
    return hmac.compare_digest(_legacy_hash_password(password), stored_hash)


def needs_password_rehash(stored_hash: Optional[str]) -> bool:
    return not bool(stored_hash and stored_hash.startswith(f"{PASSWORD_HASH_SCHEME}$"))


def enforce_password_policy(password: str) -> None:
    if len(password) < PASSWORD_MIN_LENGTH:
        raise ValueError(PASSWORD_POLICY_MESSAGE)
    if not re.search(r"[A-Z]", password):
        raise ValueError(PASSWORD_POLICY_MESSAGE)
    if not re.search(r"[a-z]", password):
        raise ValueError(PASSWORD_POLICY_MESSAGE)
    if not re.search(r"\d", password):
        raise ValueError(PASSWORD_POLICY_MESSAGE)
    if not re.search(r"[^A-Za-z0-9]", password):
        raise ValueError(PASSWORD_POLICY_MESSAGE)
