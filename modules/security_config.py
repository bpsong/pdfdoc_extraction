"""Shared production security settings for web and API responses."""

import os
import re


def is_production() -> bool:
    """Return whether deployment environment selects production safeguards."""
    environment = (
        os.getenv("APP_ENV") or os.getenv("ENV") or os.getenv("ENVIRONMENT") or "development"
    )
    return environment.strip().lower() in {"prod", "production"}


def validate_production_signing_key(value: object) -> None:
    """Reject default or short JWT signing keys in production."""
    if not is_production():
        return
    secret = value if isinstance(value, str) else ""
    normalized = re.sub(r"[^a-z0-9]", "", secret.casefold())
    if len(secret) < 32 or normalized in {"yoursecretkey", "changeme", "secretkey"}:
        raise RuntimeError("Production web.secret_key must be a unique secret of at least 32 characters")
