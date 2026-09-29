"""Production signing-key requirements without live deployment secrets."""

import pytest

from modules.security_config import validate_production_signing_key


@pytest.mark.parametrize("value", [None, "your_secret_key", "short-secret"])
def test_production_rejects_missing_placeholder_and_short_keys(monkeypatch, value: object) -> None:
    monkeypatch.setenv("APP_ENV", "production")

    with pytest.raises(RuntimeError, match="web.secret_key"):
        validate_production_signing_key(value)


def test_production_accepts_long_key_and_development_allows_local_placeholder(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    validate_production_signing_key("synthetic-production-signing-key-long-enough")

    monkeypatch.setenv("APP_ENV", "development")
    validate_production_signing_key("your_secret_key")
