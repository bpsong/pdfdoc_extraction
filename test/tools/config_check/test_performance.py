"""Performance tests for config_check validation."""

from __future__ import annotations

import time

import pytest

from tools.config_check.validator import ConfigValidator


@pytest.mark.performance
def test_validation_completes_under_300ms(config_factory) -> None:
    """Validate that a representative configuration validates within budget."""

    validator = ConfigValidator(base_dir=config_factory.paths.base_dir)
    config_path = config_factory.write()

    start = time.perf_counter()
    result = validator.validate(config_path)
    duration_ms = (time.perf_counter() - start) * 1000

    assert result.is_valid
    assert duration_ms < 300, f"Validation took {duration_ms:.1f}ms"
