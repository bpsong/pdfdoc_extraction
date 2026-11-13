#!/usr/bin/env python3
r"""Generate a bcrypt hash for legacy migration or diagnostics.

From the repository root in PowerShell:
    .\.venv\Scripts\python.exe tools\generate_password_hash.py

This utility prints a hash; it does not provision or update SQLite users. Use
tools/setup_users.py for initial accounts/recovery and Admin Users for routine
password changes. It enforces bcrypt's byte limit, not the application's password
policy. Its empty interactive input uses the legacy weak default abc1234; supply
a real password interactively and protect stdout. Command-line passwords can be
visible in shell history/process listings. See requirements.txt for bcrypt."""

import argparse
import getpass
import sys

try:
    import bcrypt  # type: ignore
except ImportError:
    import logging
    logger = logging.getLogger(__name__)
    logger.error("bcrypt is not installed. Install with: C:\\Python313\\python.exe -m pip install bcrypt")
    sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a bcrypt password hash for config.yaml")
    parser.add_argument("--password", "-p", help="Password to hash (if not provided, you will be prompted)")
    parser.add_argument("--rounds", "-r", type=int, default=12, help="Cost factor (default: 12)")
    args = parser.parse_args()

    if args.password is None:
        try:
            pwd = getpass.getpass("Enter password (default 'abc1234'): ") or "abc1234"
        except Exception:
            # Fallback for environments where getpass isn't supported
            import logging
            logger = logging.getLogger(__name__)
            logger.warning("getpass not supported in this environment; falling back to visible stdin prompt.")
            sys.stdout.write("Enter password (input will be visible). Default 'abc1234': ")
            sys.stdout.flush()
            line = sys.stdin.readline().rstrip("\n")
            pwd = line or "abc1234"
    else:
        pwd = args.password

    if not isinstance(pwd, str):
        import logging
        logger = logging.getLogger(__name__)
        logger.error("Password must be a string")
        sys.exit(1)

    try:
        hashed = bcrypt.hashpw(pwd.encode("utf-8"), bcrypt.gensalt(rounds=args.rounds)).decode("utf-8")
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.exception("Failed to generate bcrypt hash: %s", e)
        sys.exit(1)
 
    # For CLI tooling we still emit the generated hash to stdout (consumer may capture it)
    sys.stdout.write(f"{hashed}\n")


if __name__ == "__main__":
    main()
