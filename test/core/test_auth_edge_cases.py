from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock

import bcrypt
import pytest
from jose import JWTError

from modules.auth_utils import (
    AuthenticationSetupRequired,
    AuthError,
    AuthUtils,
    LoginRateLimitError,
    PasswordPolicyError,
    validate_password,
)
from modules.db.connection import connect
from modules.db.migrations import initialize_database
from modules.db.repositories import UserRepository
from test.helpers_sqlite import TempConfig


def _config(tmp_path: Path, extra: dict | None = None) -> TempConfig:
    tmp_path.mkdir(parents=True, exist_ok=True)
    values = {
        "web": {
            "secret_key": "test-secret-key-with-enough-entropy",
            "jwt_algorithm": "HS256",
            "token_exp_minutes": 30,
        }
    }
    if extra:
        values.update(extra)
    config = TempConfig(tmp_path / "auth.sqlite3", values)
    initialize_database(config)
    return config


def _hash(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def test_password_policy_accepts_valid_and_rejects_byte_limits():
    validate_password("ValidPassword1!")

    with pytest.raises(PasswordPolicyError, match="between 12 and 72"):
        validate_password("é" * 40 + "Aa1!")


def test_auth_configuration_parsers_and_required_secret(tmp_path):
    config = _config(
        tmp_path,
        {
            "web": {
                "secret_key": "secret",
                "token_exp_minutes": "invalid",
            },
            "auth": {
                "login_rate_limit_enabled": "off",
                "login_max_failed_attempts": 0,
                "login_window_seconds": "invalid",
                "login_cooldown_seconds": "12",
            },
        },
    )
    auth = AuthUtils(config)

    assert auth.token_exp_minutes == 30
    assert auth.login_rate_limit_enabled is False
    assert auth.login_max_failed_attempts == 5
    assert auth.login_window_seconds == 600
    assert auth.login_cooldown_seconds == 12
    assert AuthUtils._config_bool("yes", False) is True
    assert AuthUtils._config_bool("unknown", True) is True
    assert AuthUtils._positive_int(None, 7) == 7

    missing_secret = _config(tmp_path / "missing", {"web": {"secret_key": None}})
    with pytest.raises(AuthError, match="secret_key"):
        AuthUtils(missing_secret)


def test_password_verification_handles_missing_and_bcrypt_errors(tmp_path, monkeypatch):
    auth = AuthUtils(_config(tmp_path))

    assert auth.verify_password(None, "hash") is False
    monkeypatch.setattr(
        "modules.auth_utils.bcrypt.checkpw",
        Mock(side_effect=ValueError("too long")),
    )
    assert auth.verify_password("password", "hash") is False
    monkeypatch.setattr(
        "modules.auth_utils.bcrypt.checkpw",
        Mock(side_effect=RuntimeError("backend")),
    )
    assert auth.verify_password("password", "hash") is False


def test_token_creation_and_decode_failure(tmp_path, monkeypatch):
    auth = AuthUtils(_config(tmp_path))

    token = auth.create_access_token({"sub": "admin"}, expires_delta=timedelta(minutes=1))
    assert auth.decode_token(token)["sub"] == "admin"

    monkeypatch.setattr(
        "modules.auth_utils.jwt.decode",
        Mock(side_effect=JWTError("bad token")),
    )
    with pytest.raises(AuthError, match="Invalid token"):
        auth.decode_token("broken")


def test_login_reports_setup_unknown_user_and_invalid_password(tmp_path, monkeypatch):
    config = _config(tmp_path)
    auth = AuthUtils(config)

    with pytest.raises(AuthenticationSetupRequired):
        auth.login("admin", "anything")

    with connect(config) as conn:
        UserRepository(conn).initialize(
            {
                "admin": _hash("AdminPassword1!"),
                "operator": _hash("OperatorPass1!"),
            }
        )

    with pytest.raises(AuthError, match="Invalid credentials"):
        auth.login("missing", "anything")

    monkeypatch.setattr(auth, "verify_password", lambda *args: False)
    with pytest.raises(AuthError, match="Invalid credentials"):
        auth.login("admin", "wrong")


def test_rate_limit_disabled_expired_lock_and_window_pruning(tmp_path, monkeypatch):
    auth = AuthUtils(
        _config(
            tmp_path,
            {
                "auth": {
                    "login_max_failed_attempts": 2,
                    "login_window_seconds": 10,
                    "login_cooldown_seconds": 20,
                }
            },
        )
    )
    AuthUtils.reset_login_rate_limits()
    key = auth._login_rate_limit_key(" Admin ", " Client ")
    assert key == "client:admin"

    monkeypatch.setattr("modules.auth_utils.time.monotonic", lambda: 100.0)
    auth._failed_login_attempts[key] = [80.0, 95.0]
    assert auth._ensure_login_not_rate_limited("admin", "client") == key
    assert auth._failed_login_attempts[key] == [95.0]

    auth._locked_login_keys[key] = 110.0
    with pytest.raises(LoginRateLimitError, match="10 seconds"):
        auth._ensure_login_not_rate_limited("admin", "client")

    monkeypatch.setattr("modules.auth_utils.time.monotonic", lambda: 120.0)
    assert auth._ensure_login_not_rate_limited("admin", "client") == key
    assert key not in auth._locked_login_keys

    auth.login_rate_limit_enabled = False
    auth._record_failed_login(key)
    assert auth._ensure_login_not_rate_limited("", "") == "unknown:<blank>"


def test_get_current_user_rejects_invalid_payloads_and_wraps_errors(tmp_path, monkeypatch):
    config = _config(tmp_path)
    with connect(config) as conn:
        UserRepository(conn).initialize(
            {
                "admin": _hash("AdminPassword1!"),
                "operator": _hash("OperatorPass1!"),
            }
        )
    auth = AuthUtils(config)

    monkeypatch.setattr(auth, "decode_token", lambda token: {})
    with pytest.raises(AuthError, match="missing subject"):
        auth.get_current_user("token")

    monkeypatch.setattr(auth, "decode_token", lambda token: {"sub": "missing"})
    with pytest.raises(AuthError, match="Invalid token subject"):
        auth.get_current_user("token")

    monkeypatch.setattr(
        auth,
        "decode_token",
        lambda token: {"sub": "admin", "role": "operator", "ver": 1},
    )
    with pytest.raises(AuthError, match="revoked"):
        auth.get_current_user("token")

    monkeypatch.setattr(auth, "decode_token", Mock(side_effect=RuntimeError("decode backend")))
    with pytest.raises(AuthError, match="Token validation error"):
        auth.get_current_user("token")

    assert auth.is_admin("admin") is True
    assert auth.is_admin("operator") is False
    assert auth.is_admin("missing") is False
