import logging
from pathlib import Path

import bcrypt
import pytest

from modules.auth_utils import AuthError, AuthUtils, LoginRateLimitError
from modules.db.connection import connect
from modules.db.migrations import initialize_database
from modules.db.repositories import UserRepository


class AuthConfig:
    """Minimal config stub for AuthUtils logging tests."""

    def __init__(
        self,
        password_hash: str,
        db_path: Path,
        *,
        login_max_failed_attempts: int = 5,
        login_window_seconds: int = 600,
        login_cooldown_seconds: int = 600,
    ) -> None:
        self.password_hash = password_hash
        self.login_max_failed_attempts = login_max_failed_attempts
        self.login_window_seconds = login_window_seconds
        self.login_cooldown_seconds = login_cooldown_seconds
        self._config_path = db_path.parent / "config.yaml"
        self.db_path = db_path

    def get(self, key: str, default=None):
        values = {
            "database.path": str(self.db_path),
            "web.secret_key": "test-secret-key-with-enough-entropy",
            "web.jwt_algorithm": "HS256",
            "web.token_exp_minutes": 30,
            "auth.login_rate_limit_enabled": True,
            "auth.login_max_failed_attempts": self.login_max_failed_attempts,
            "auth.login_window_seconds": self.login_window_seconds,
            "auth.login_cooldown_seconds": self.login_cooldown_seconds,
        }
        return values.get(key, default)


def build_auth(tmp_path: Path, password_hash: str, **kwargs) -> AuthUtils:
    """Create initialized SQLite authentication for a test."""
    config = AuthConfig(password_hash, tmp_path / "auth.sqlite3", **kwargs)
    initialize_database(config)
    operator_hash = bcrypt.hashpw(b"Operator123!", bcrypt.gensalt()).decode()
    with connect(config) as conn:
        UserRepository(conn).initialize({"admin": password_hash, "operator": operator_hash})
    return AuthUtils(config)


def test_auth_logs_do_not_include_password_hash(caplog, tmp_path):
    password_hash = bcrypt.hashpw(b"secret", bcrypt.gensalt()).decode("utf-8")
    caplog.set_level(logging.DEBUG)
    AuthUtils.reset_login_rate_limits()

    auth = build_auth(tmp_path, password_hash)
    auth.login("admin", "secret")

    assert password_hash not in caplog.text


def test_login_rate_limit_blocks_after_repeated_failures(tmp_path):
    password_hash = bcrypt.hashpw(b"secret", bcrypt.gensalt()).decode("utf-8")
    AuthUtils.reset_login_rate_limits()
    auth = build_auth(tmp_path, password_hash, login_max_failed_attempts=2)

    for _ in range(2):
        with pytest.raises(AuthError):
            auth.login("admin", "wrong", client_id="127.0.0.1")

    with pytest.raises(LoginRateLimitError):
        auth.login("admin", "wrong", client_id="127.0.0.1")


def test_successful_login_resets_failed_attempts(tmp_path):
    password_hash = bcrypt.hashpw(b"secret", bcrypt.gensalt()).decode("utf-8")
    AuthUtils.reset_login_rate_limits()
    auth = build_auth(tmp_path, password_hash, login_max_failed_attempts=2)

    with pytest.raises(AuthError):
        auth.login("admin", "wrong", client_id="127.0.0.1")

    auth.login("admin", "secret", client_id="127.0.0.1")

    with pytest.raises(AuthError):
        auth.login("admin", "wrong", client_id="127.0.0.1")
