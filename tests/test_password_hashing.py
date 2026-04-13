import hashlib

from src import main as app_module
from src.utils import security as security_module


def test_hash_password_uses_pbkdf2_scheme():
    encoded = app_module.hash_password("Secreta123!")
    assert encoded.startswith(f"{app_module.PASSWORD_HASH_SCHEME}$")
    assert app_module.verify_password("Secreta123!", encoded) is True
    assert app_module.verify_password("incorrecta", encoded) is False
    assert app_module.needs_password_rehash(encoded) is False


def test_verify_password_supports_legacy_sha256():
    legacy = hashlib.sha256("Admin123!".encode("utf-8")).hexdigest()
    assert app_module.verify_password("Admin123!", legacy) is True
    assert app_module.needs_password_rehash(legacy) is True


def test_password_defaults_are_consistent_across_modules():
    assert app_module.DEFAULT_ADMIN_PASSWORD == security_module.DEFAULT_ADMIN_PASSWORD
    assert app_module.DEFAULT_VENDOR_PASSWORD == security_module.DEFAULT_VENDOR_PASSWORD
