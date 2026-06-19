"""Tests for SQLite-backed fixed user authentication and password management."""

from __future__ import annotations

from pathlib import Path

import bcrypt
import pytest

from modules.auth_utils import AuthError, AuthUtils, PasswordPolicyError, validate_password
from modules.db.connection import connect
from modules.db.migrations import initialize_database
from modules.db.repositories import UserRepository
from modules.services.user_service import UserService, UserServiceError
from test.helpers_sqlite import TempConfig
from tools.setup_users import _legacy_admin_hash


def _config(tmp_path: Path) -> TempConfig:
    config = TempConfig(
        tmp_path / "users.sqlite3",
        {"web": {"secret_key": "test-secret-key-with-enough-entropy"}},
    )
    initialize_database(config)
    return config


def _hash(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def test_fixed_users_initialize_once(tmp_path: Path) -> None:
    config = _config(tmp_path)
    with connect(config) as conn:
        repository = UserRepository(conn)
        repository.initialize({"admin": _hash("AdminPassword1!"), "operator": _hash("OperatorPass1!")})
        assert [(user["username"], user["role"]) for user in repository.list()] == [
            ("admin", "admin"), ("operator", "operator")
        ]
        with pytest.raises(ValueError, match="already initialized"):
            repository.initialize({"admin": _hash("AdminPassword1!"), "operator": _hash("OperatorPass1!")})


def test_legacy_admin_hash_import(tmp_path: Path) -> None:
    legacy_hash = _hash("AdminPassword1!")
    legacy = tmp_path / "legacy.yaml"
    legacy.write_text(
        f'authentication:\n  username: "admin"\n  password_hash: "{legacy_hash}"\n',
        encoding="utf-8",
    )
    assert _legacy_admin_hash(legacy) == legacy_hash


@pytest.mark.parametrize("password", ["shortA1!", "alllowercase1!", "ALLUPPERCASE1!", "NoNumbersHere!", "NoSymbolsHere1"])
def test_password_policy_rejects_invalid_values(password: str) -> None:
    with pytest.raises(PasswordPolicyError):
        validate_password(password)


def test_both_users_login_and_password_change_revokes_target(tmp_path: Path) -> None:
    config = _config(tmp_path)
    with connect(config) as conn:
        UserRepository(conn).initialize(
            {"admin": _hash("AdminPassword1!"), "operator": _hash("OperatorPass1!")}
        )
    auth = AuthUtils(config)
    admin_token = auth.login("admin", "AdminPassword1!")
    operator_token = auth.login("operator", "OperatorPass1!")
    assert auth.get_current_user(admin_token) == "admin"
    assert auth.get_current_user(operator_token) == "operator"

    with connect(config) as conn:
        UserService(conn).change_password(
            actor="admin",
            target="operator",
            current_admin_password="AdminPassword1!",
            new_password="ReplacementPass2!",
            confirmation="ReplacementPass2!",
        )
    with pytest.raises(AuthError, match="revoked"):
        auth.get_current_user(operator_token)
    assert auth.get_current_user(admin_token) == "admin"
    assert auth.login("operator", "ReplacementPass2!")


def test_password_change_requires_admin_password_and_rejects_reuse(tmp_path: Path) -> None:
    config = _config(tmp_path)
    with connect(config) as conn:
        UserRepository(conn).initialize(
            {"admin": _hash("AdminPassword1!"), "operator": _hash("OperatorPass1!")}
        )
        service = UserService(conn)
        with pytest.raises(UserServiceError, match="incorrect"):
            service.change_password(actor="admin", target="operator", current_admin_password="wrong",
                                    new_password="ReplacementPass2!", confirmation="ReplacementPass2!")
        with pytest.raises(UserServiceError, match="differ"):
            service.change_password(actor="admin", target="operator", current_admin_password="AdminPassword1!",
                                    new_password="OperatorPass1!", confirmation="OperatorPass1!")
