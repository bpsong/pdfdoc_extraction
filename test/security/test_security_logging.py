import logging

import bcrypt
import pytest

from modules.auth_utils import AuthError, AuthUtils, LoginRateLimitError


class AuthConfig:
    """Minimal config stub for AuthUtils logging tests."""

    def __init__(
        self,
        password_hash: str,
        *,
        login_max_failed_attempts: int = 5,
        login_window_seconds: int = 600,
        login_cooldown_seconds: int = 600,
    ) -> None:
        self.password_hash = password_hash
        self.login_max_failed_attempts = login_max_failed_attempts
        self.login_window_seconds = login_window_seconds
        self.login_cooldown_seconds = login_cooldown_seconds

    def get(self, key: str, default=None):
        values = {
            "authentication.username": "admin",
            "authentication.password_hash": self.password_hash,
            "web.secret_key": "test-secret-key-with-enough-entropy",
            "web.jwt_algorithm": "HS256",
            "web.token_exp_minutes": 30,
            "auth.login_rate_limit_enabled": True,
            "auth.login_max_failed_attempts": self.login_max_failed_attempts,
            "auth.login_window_seconds": self.login_window_seconds,
            "auth.login_cooldown_seconds": self.login_cooldown_seconds,
        }
        return values.get(key, default)


def test_auth_logs_do_not_include_password_hash(caplog):
    password_hash = bcrypt.hashpw(b"secret", bcrypt.gensalt()).decode("utf-8")
    caplog.set_level(logging.DEBUG)
    AuthUtils.reset_login_rate_limits()

    auth = AuthUtils(AuthConfig(password_hash))
    auth.login("admin", "secret")

    assert password_hash not in caplog.text


def test_login_rate_limit_blocks_after_repeated_failures():
    password_hash = bcrypt.hashpw(b"secret", bcrypt.gensalt()).decode("utf-8")
    AuthUtils.reset_login_rate_limits()
    auth = AuthUtils(AuthConfig(password_hash, login_max_failed_attempts=2))

    for _ in range(2):
        with pytest.raises(AuthError):
            auth.login("admin", "wrong", client_id="127.0.0.1")

    with pytest.raises(LoginRateLimitError):
        auth.login("admin", "wrong", client_id="127.0.0.1")


def test_successful_login_resets_failed_attempts():
    password_hash = bcrypt.hashpw(b"secret", bcrypt.gensalt()).decode("utf-8")
    AuthUtils.reset_login_rate_limits()
    auth = AuthUtils(AuthConfig(password_hash, login_max_failed_attempts=2))

    with pytest.raises(AuthError):
        auth.login("admin", "wrong", client_id="127.0.0.1")

    auth.login("admin", "secret", client_id="127.0.0.1")

    with pytest.raises(AuthError):
        auth.login("admin", "wrong", client_id="127.0.0.1")
