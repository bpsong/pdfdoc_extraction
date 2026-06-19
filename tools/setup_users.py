"""Initialize the fixed admin and operator users in SQLite.

Run with: C:\\Python313\\python.exe tools\\setup_users.py --config config.yaml
"""

from __future__ import annotations

import argparse
import getpass
from pathlib import Path
import sys

import bcrypt
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules.auth_utils import PasswordPolicyError, validate_password  # noqa: E402
from modules.config_manager import ConfigManager  # noqa: E402
from modules.db.connection import connect  # noqa: E402
from modules.db.migrations import initialize_database  # noqa: E402
from modules.db.repositories import UserRepository  # noqa: E402


def _prompt_password(label: str) -> str:
    """Prompt twice until a policy-compliant password is supplied."""
    password = getpass.getpass(f"{label} password: ")
    confirmation = getpass.getpass(f"Confirm {label} password: ")
    if password != confirmation:
        raise ValueError(f"{label} passwords do not match")
    validate_password(password)
    return password


def _legacy_admin_hash(path: Path) -> str:
    """Read and validate a bcrypt admin hash from legacy YAML."""
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    value = str((data.get("authentication") or {}).get("password_hash") or "")
    if not value.startswith(("$2a$", "$2b$", "$2y$")):
        raise ValueError("Legacy YAML does not contain a valid bcrypt password hash")
    return value


def main() -> int:
    """Parse arguments and initialize both fixed accounts."""
    parser = argparse.ArgumentParser(description="Initialize SQLite application users")
    parser.add_argument("--config", default="config.yaml", help="Runtime YAML configuration")
    parser.add_argument("--legacy-config", help="Import the legacy admin bcrypt hash")
    parser.add_argument("--reset", action="store_true", help="Replace both existing users")
    args = parser.parse_args()
    try:
        config = ConfigManager(Path(args.config).resolve())
        initialize_database(config)
        admin_hash = (
            _legacy_admin_hash(Path(args.legacy_config))
            if args.legacy_config
            else bcrypt.hashpw(_prompt_password("Admin").encode(), bcrypt.gensalt(12)).decode()
        )
        operator_hash = bcrypt.hashpw(_prompt_password("Operator").encode(), bcrypt.gensalt(12)).decode()
        with connect(config) as conn:
            UserRepository(conn).initialize(
                {"admin": admin_hash, "operator": operator_hash}, overwrite=args.reset
            )
        print("Initialized admin and operator users.")
        return 0
    except (OSError, ValueError, PasswordPolicyError) as exc:
        print(f"User setup failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
