"""Business rules for fixed SQLite-backed application users."""

from __future__ import annotations

import sqlite3
from typing import Any, NoReturn

import bcrypt

from modules.auth_utils import PasswordPolicyError, validate_password
from modules.db.repositories import AuditRepository, FIXED_USERS, UserRepository


class UserServiceError(ValueError):
    """Raised for rejected user-management operations."""


class UserService:
    """List users and change passwords for the fixed accounts."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.users = UserRepository(conn)
        self.audit = AuditRepository(conn)

    def list_users(self) -> list[dict[str, Any]]:
        """Return non-secret user metadata."""
        return self.users.list()

    @staticmethod
    def _matches(password: str, password_hash: str) -> bool:
        """Safely compare a candidate with a bcrypt hash."""
        try:
            return bcrypt.checkpw(password.encode(), password_hash.encode())
        except ValueError:
            return False

    def _reject(self, actor: str, target: str, message: str) -> NoReturn:
        """Audit a rejected password change without credential material."""
        self.audit.append(
            event_type="admin_user_password_change_rejected",
            event={"target": target, "outcome": "rejected", "reason": message},
            user=actor,
        )
        raise UserServiceError(message)

    def change_password(
        self,
        *,
        actor: str,
        target: str,
        current_admin_password: str,
        new_password: str,
        confirmation: str,
    ) -> dict[str, Any]:
        """Change a password after authenticating the admin actor."""
        admin = self.users.get(actor)
        target_user = self.users.get(target)
        if not admin or admin["role"] != "admin":
            self._reject(actor, target, "Admin role required")
        if target not in FIXED_USERS or not target_user:
            self._reject(actor, target, "Unknown user")
        if not self._matches(current_admin_password, admin["password_hash"]):
            self._reject(actor, target, "Current admin password is incorrect")
        if new_password != confirmation:
            self._reject(actor, target, "New password and confirmation do not match")
        try:
            validate_password(new_password)
        except PasswordPolicyError as exc:
            self._reject(actor, target, str(exc))
        if self._matches(new_password, target_user["password_hash"]):
            self._reject(actor, target, "New password must differ from the current password")
        password_hash = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt(rounds=12)).decode()
        self.users.update_password(target, password_hash)
        updated = self.users.get(target)
        if updated is None:
            raise UserServiceError("Updated user could not be loaded")
        self.audit.append(
            event_type="admin_user_password_changed",
            event={"target": target, "outcome": "success"},
            user=actor,
        )
        return {key: updated[key] for key in ("username", "role", "token_version", "password_updated_at")}
