import logging

import bcrypt

from modules.auth_utils import AuthUtils


class AuthConfig:
    """Minimal config stub for AuthUtils logging tests."""

    def __init__(self, password_hash: str) -> None:
        self.password_hash = password_hash

    def get(self, key: str, default=None):
        values = {
            "authentication.username": "admin",
            "authentication.password_hash": self.password_hash,
            "web.secret_key": "test-secret-key-with-enough-entropy",
            "web.jwt_algorithm": "HS256",
            "web.token_exp_minutes": 30,
        }
        return values.get(key, default)


def test_auth_logs_do_not_include_password_hash(caplog):
    password_hash = bcrypt.hashpw(b"secret", bcrypt.gensalt()).decode("utf-8")
    caplog.set_level(logging.DEBUG)

    auth = AuthUtils(AuthConfig(password_hash))
    auth.login("admin", "secret")

    assert password_hash not in caplog.text
